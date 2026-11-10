"""Browser smoke test: each role can do its main job in the real frontend.

Runs the real app (uvicorn in a thread) against the test database and drives Chromium with
Playwright. Skipped when Playwright is not installed (it lives in requirements-dev.txt).
Install: py -m pip install -r requirements-dev.txt && py -m playwright install chromium
"""

import re
import socket
import threading
import time

import pytest

playwright_api = pytest.importorskip("playwright.sync_api")

import uvicorn  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Location, Product, ProductUnit, UserRole  # noqa: E402
from app.rate_limit import limiter  # noqa: E402
from app.services import movements  # noqa: E402

expect = playwright_api.expect
PASSWORD = "password123"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_server(test_engine, db):
    """The app on a real port. Each request gets its own session on the test database."""
    Session = sessionmaker(bind=test_engine, autoflush=False)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    limiter.reset()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("live server did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """A fresh page that fails the test on any JS error or CSP violation."""
    context = browser.new_context()
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: (
            errors.append(msg.text)
            # Expected API refusals (wrong password, conflicts) are logged by the browser; not bugs.
            if msg.type == "error" and not re.search(r"status of (401|403|409|422)", msg.text)
            else None
        ),
    )
    yield page
    context.close()
    assert errors == [], f"browser errors: {errors}"


@pytest.fixture
def warehouse(db, make_user):
    """Three users, one product with 20 pcs on A-01-03, and an empty B-02-01."""
    admin = make_user(UserRole.ADMIN, email="admin@test.local", name="Ada Admin")
    worker = make_user(UserRole.WORKER, email="worker@test.local", name="Wes Worker")
    planner = make_user(UserRole.PLANNER, email="planner@test.local", name="Pia Planner")
    product = Product(sku="CABLE-01", name="USB cable", unit=ProductUnit.PCS, reorder_point=10)
    shelf = Location(code="A-01-03")
    other = Location(code="B-02-01")
    db.add_all([product, shelf, other])
    db.commit()
    movements.receive(db, admin, product.id, shelf.id, 20, None)
    return {"admin": admin, "worker": worker, "planner": planner, "product": product}


def login(page, base_url: str, email: str):
    page.goto(f"{base_url}/app/")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Log in").click()


def test_root_shows_login(live_server, page):
    page.goto(live_server)

    expect(page).to_have_url(f"{live_server}/app/")
    expect(page.get_by_role("heading", name="Log in")).to_be_visible()


def test_wrong_password_shows_message(live_server, page, warehouse):
    page.goto(f"{live_server}/app/")
    page.get_by_label("Email").fill("worker@test.local")
    page.get_by_label("Password").fill("wrong-password")
    page.get_by_role("button", name="Log in").click()

    expect(page.get_by_text("Wrong email or password")).to_be_visible()


def test_worker_picks_stock_and_sees_conflict(live_server, page, warehouse):
    login(page, live_server, "worker@test.local")
    expect(page).to_have_url(re.compile(r"/app/operations\.html$"))

    # Workers do not see admin pages in the menu.
    expect(page.get_by_role("link", name="Users")).to_have_count(0)

    page.get_by_text("Pick", exact=True).click()
    page.get_by_label("Product").select_option(label="CABLE-01 | USB cable")
    page.get_by_label("From location").select_option(label="A-01-03 (20 pcs)")
    page.get_by_label("Quantity").fill("5")
    page.get_by_role("button", name="Pick stock").click()
    expect(page.get_by_text("Picked 5 pcs of CABLE-01 from A-01-03")).to_be_visible()
    expect(page.get_by_text("A-01-03 now holds 15 pcs.")).to_be_visible()

    page.get_by_label("From location").select_option(label="A-01-03 (15 pcs)")
    page.get_by_label("Quantity").fill("99")
    page.get_by_role("button", name="Pick stock").click()
    expect(page.get_by_text("Insufficient stock")).to_be_visible()


def test_worker_cannot_open_admin_page(live_server, page, warehouse):
    login(page, live_server, "worker@test.local")
    expect(page).to_have_url(re.compile(r"/app/operations\.html$"))

    page.goto(f"{live_server}/app/users.html")

    expect(page.get_by_role("heading", name="No access")).to_be_visible()


def test_planner_sees_planner_and_changes_reorder_point(live_server, page, warehouse):
    login(page, live_server, "planner@test.local")
    expect(page).to_have_url(re.compile(r"/app/planner\.html$"))
    expect(page.get_by_role("link", name="CABLE-01")).to_be_visible()
    expect(page.get_by_role("link", name="Stock operations")).to_have_count(0)

    page.get_by_role("link", name="CABLE-01").click()
    page.get_by_label("Reorder point").fill("50")
    page.get_by_role("button", name="Save reorder point").click()

    expect(page.get_by_text("Reorder point saved: 50.")).to_be_visible()
    expect(page.get_by_text("Below reorder point")).to_be_visible()


def test_admin_adds_location(live_server, page, warehouse):
    login(page, live_server, "admin@test.local")
    expect(page).to_have_url(re.compile(r"/app/stock\.html$"))

    page.get_by_role("link", name="Locations").click()
    page.get_by_label("Code").fill("c-03-07")
    page.get_by_role("button", name="Add location").click()

    expect(page.get_by_text("Added C-03-07.")).to_be_visible()
    expect(page.get_by_role("link", name="C-03-07")).to_be_visible()


def test_logout_returns_to_login(live_server, page, warehouse):
    login(page, live_server, "admin@test.local")
    expect(page).to_have_url(re.compile(r"/app/stock\.html$"))

    page.get_by_role("button", name="Log out").click()

    expect(page.get_by_text("You are logged out.")).to_be_visible()
    page.goto(f"{live_server}/app/stock.html")
    expect(page.get_by_role("heading", name="Log in")).to_be_visible()


def test_demo_login_buttons_log_in_with_one_click(live_server, page, db, monkeypatch):
    # Set after the server started, so the app's startup doesn't seed the dev database.
    from app.config import settings
    from app.demo import reset_demo

    reset_demo(db)
    monkeypatch.setattr(settings, "demo_mode", True)

    page.goto(f"{live_server}/app/")
    page.get_by_role("button", name=re.compile("Planner")).click()

    expect(page).to_have_url(re.compile(r"/app/planner\.html$"))
    expect(page.get_by_role("link", name="BOX-M")).to_be_visible()


def test_no_demo_logins_outside_demo_mode(live_server, page):
    page.goto(f"{live_server}/app/")

    expect(page.get_by_role("heading", name="Log in")).to_be_visible()
    expect(page.get_by_role("heading", name="Try the demo")).to_be_hidden()
