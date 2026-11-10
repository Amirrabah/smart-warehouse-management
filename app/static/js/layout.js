// Shared page frame: checks the login, draws the role-based menu, the notification badge and logout.
// Hiding a menu item is only a convenience. The API's 403 is the real block.

import { api, getToken, goToLogin } from "./api.js";
import { $, clear, el } from "./dom.js";

export const ROLES = {
  admin: "Admin",
  worker: "Warehouse worker",
  planner: "Planner",
};

export const can = {
  operate: (user) => user.role === "admin" || user.role === "worker",
  setReorderPoint: (user) => user.role === "admin" || user.role === "planner",
  readInbox: (user) => user.role === "admin" || user.role === "planner",
  manage: (user) => user.role === "admin",
};

const MENU = [
  {
    heading: "Stock",
    items: [
      { href: "stock.html", text: "Stock overview" },
      { href: "operations.html", text: "Stock operations", show: can.operate },
      { href: "shelf.html", text: "Shelves" },
      { href: "history.html", text: "Movement history" },
    ],
  },
  {
    heading: "Planning",
    items: [
      { href: "planner.html", text: "Planner" },
      { href: "notifications.html", text: "Notifications", show: can.readInbox, badge: true },
    ],
  },
  {
    heading: "Admin",
    items: [
      { href: "products.html", text: "Products", show: can.manage },
      { href: "locations.html", text: "Locations", show: can.manage },
      { href: "users.html", text: "Users", show: can.manage },
    ],
  },
];

export function homeFor(user) {
  if (user.role === "worker") return "operations.html";
  if (user.role === "planner") return "planner.html";
  return "stock.html";
}

let badge = null;

/** Update the unread count next to "Notifications". Uses total of a 1-item page. */
export async function refreshBadge() {
  if (!badge) return;
  try {
    const page = await api("/notifications", { params: { unread: true, limit: 1 } });
    badge.textContent = page.total > 99 ? "99+" : String(page.total);
    badge.hidden = page.total === 0;
    badge.setAttribute("aria-label", `${page.total} unread`);
  } catch {
    badge.hidden = true;
  }
}

function currentPage() {
  const name = window.location.pathname.split("/").pop();
  return name || "index.html";
}

function buildSidebar(user) {
  const here = currentPage();
  const nav = el("nav", { className: "sidebar", id: "sidebar", "aria-label": "Main" });
  nav.append(brand());

  for (const group of MENU) {
    const visible = group.items.filter((item) => !item.show || item.show(user));
    if (visible.length === 0) continue;
    nav.append(el("div", { className: "nav-heading", text: group.heading }));
    const list = el("ul", { className: "nav-group" });
    for (const item of visible) {
      const link = el("a", {
        className: "nav-link",
        href: item.href,
        "aria-current": item.href === here ? "page" : null,
      });
      link.append(el("span", { text: item.text }));
      if (item.badge) {
        badge = el("span", { className: "badge", hidden: true });
        link.append(badge);
      }
      list.append(el("li", {}, link));
    }
    nav.append(list);
  }

  const logout = el("button", { type: "button", className: "btn btn-on-dark", text: "Log out" });
  logout.addEventListener("click", () => goToLogin("logout"));
  nav.append(
    el(
      "div",
      { className: "who" },
      el("div", { className: "who-name", text: user.name }),
      el("div", { className: "who-role", text: ROLES[user.role] || user.role }),
      logout,
    ),
  );
  return nav;
}

function brand() {
  return el(
    "a",
    { className: "brand", href: "stock.html" },
    el("span", { className: "brand-mark", "aria-hidden": "true", text: "SW" }),
    "Smart Warehouse",
  );
}

function buildTopbar(shell) {
  const toggle = el("button", {
    type: "button",
    className: "btn btn-quiet btn-small btn-on-dark",
    "aria-expanded": "false",
    "aria-controls": "sidebar",
    text: "Menu",
  });
  toggle.addEventListener("click", () => {
    const open = shell.classList.toggle("nav-open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  return el("header", { className: "topbar" }, brand(), el("div", {}, toggle));
}

/**
 * Start a logged-in page. roles: which roles the page is for (omit = everyone).
 * Returns the user, or null when the page should not render (not allowed / redirecting).
 */
export async function startPage({ roles } = {}) {
  if (!getToken()) {
    goToLogin();
    return null;
  }
  let user;
  try {
    user = await api("/auth/me");
  } catch {
    // 401 already redirected; anything else: back to login with a reason.
    goToLogin("error");
    return null;
  }

  const shell = $("#shell");
  const main = $("#main");
  shell.prepend(buildTopbar(shell), buildSidebar(user));
  main.hidden = false;

  if (badge) refreshBadge();

  if (roles && !roles.includes(user.role)) {
    const allowed = roles.map((role) => ROLES[role]).join(", ");
    clear(main).append(
      el(
        "div",
        { className: "page-head" },
        el("div", {}, el("h1", { text: "No access" })),
      ),
      el("p", { className: "msg msg-info", text: `This page is for: ${allowed}.` }),
      el("p", {}, el("a", { href: homeFor(user), text: "Go to your start page" })),
    );
    return null;
  }
  return user;
}
