import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"
HTML_PAGES = sorted(STATIC_DIR.glob("*.html"))
JS_FILES = sorted(STATIC_DIR.rglob("*.js"))

INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
INLINE_HANDLER = re.compile(r"<[^>]+\son[a-z]+\s*=", re.IGNORECASE)
INLINE_STYLE = re.compile(r"<style|\sstyle\s*=", re.IGNORECASE)
SCRIPT_SRC = re.compile(r'<script[^>]*\bsrc="([^"]+)"', re.IGNORECASE)
# Ways to turn a string into HTML. API data must only reach the page via textContent.
UNSAFE_JS = re.compile(r"\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write|\beval\(")


# --- Serving the frontend -------------------------------------------------


def test_root_redirects_to_app():
    response = client.get("/", follow_redirects=False)

    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/app/"


def test_app_serves_login_page():
    response = client.get("/app/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'id="login-form"' in response.text


def test_js_is_served_as_javascript():
    # Module scripts are refused by the browser unless the MIME type is JavaScript.
    # On Windows the registry can map .js to text/plain, so main.py pins it.
    response = client.get("/app/js/api.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_css_is_served_as_css():
    response = client.get("/app/css/style.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_unknown_static_file_is_404():
    assert client.get("/app/does-not-exist.html").status_code == 404


def test_api_routes_still_work_next_to_the_frontend():
    assert client.get("/health").json() == {"status": "ok"}


# --- Security headers -----------------------------------------------------


def test_csp_blocks_inline_scripts_on_frontend():
    csp = client.get("/app/").headers["content-security-policy"]

    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


def test_basic_security_headers_on_api_responses():
    headers = client.get("/health").headers

    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "content-security-policy" in headers


def test_docs_page_has_no_csp_so_swagger_still_works():
    response = client.get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


# --- Rules for every page and script (CSP + XSS) --------------------------


def test_there_are_pages_to_check():
    names = {page.name for page in HTML_PAGES}

    assert {
        "index.html",
        "stock.html",
        "product.html",
        "operations.html",
        "history.html",
        "planner.html",
        "notifications.html",
        "shelf.html",
        "products.html",
        "locations.html",
        "users.html",
    } <= names


@pytest.mark.parametrize("page", HTML_PAGES, ids=lambda p: p.name)
def test_page_has_no_inline_js_or_css(page: Path):
    html = page.read_text(encoding="utf-8")

    assert not INLINE_SCRIPT.search(html), "use <script src=...>, never inline <script>"
    assert not INLINE_HANDLER.search(html), "use addEventListener, never onclick=..."
    assert not INLINE_STYLE.search(html), "put styles in css/style.css"


@pytest.mark.parametrize("page", HTML_PAGES, ids=lambda p: p.name)
def test_page_scripts_exist_and_are_served(page: Path):
    html = page.read_text(encoding="utf-8")
    sources = SCRIPT_SRC.findall(html)

    assert sources, "every page loads its script"
    for src in sources:
        assert client.get(f"/app/{src}").status_code == 200, src


@pytest.mark.parametrize("script", JS_FILES, ids=lambda p: p.name)
def test_script_never_builds_html_from_strings(script: Path):
    code = script.read_text(encoding="utf-8")

    assert not UNSAFE_JS.search(code), "use textContent / createElement instead"


def test_hsts_only_over_https():
    # Behind Railway, uvicorn --proxy-headers turns X-Forwarded-Proto: https into an https scheme.
    https = TestClient(app, base_url="https://testserver")

    assert "max-age=" in https.get("/health").headers["strict-transport-security"]
    assert "strict-transport-security" not in client.get("/health").headers  # local http
