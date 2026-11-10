import { api, ApiError, clearToken, getToken, setToken } from "./api.js";
import { $, busy, clear, el, queryParam, setMessage } from "./dom.js";
import { homeFor, ROLES } from "./layout.js";

const REASONS = {
  expired: ["Your session ended. Log in again.", "info"],
  logout: ["You are logged out.", "ok"],
  error: ["Something went wrong loading the page. Log in again.", "error"],
};

async function goHome() {
  const user = await api("/auth/me");
  window.location.replace(homeFor(user));
}

async function init() {
  const form = $("#login-form");
  const message = $("#login-message");
  const reason = REASONS[queryParam("reason")];
  if (reason) setMessage(message, reason[0], reason[1]);

  // Already logged in in this tab: skip the form.
  if (getToken()) {
    try {
      await goHome();
      return;
    } catch {
      clearToken();
    }
  }

  async function logIn(email, password, button) {
    await busy(button, async () => {
      try {
        const data = await api("/auth/login", {
          method: "POST",
          body: { email, password },
          auth: false,
        });
        setToken(data.access_token);
        await goHome();
      } catch (error) {
        const text =
          error instanceof ApiError && error.status === 401
            ? "Wrong email or password, or the account is deactivated."
            : error.message;
        setMessage(message, text);
        form.password.value = "";
        form.password.focus();
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = form.email.value.trim();
    const password = form.password.value;
    if (!email || !password) {
      setMessage(message, "Enter your email and password.");
      return;
    }
    await logIn(email, password, form.querySelector('button[type="submit"]'));
  });
  form.email.focus();
  showDemoLogins(logIn);
}

// In demo mode the API lists one public login per role; show them as one-click buttons.
async function showDemoLogins(logIn) {
  let accounts = [];
  try {
    accounts = await api("/auth/demo-accounts", { auth: false });
  } catch {
    return;
  }
  if (!accounts.length) return;
  const list = clear($("#demo-logins"));
  for (const account of accounts) {
    const button = el(
      "button",
      { type: "button", className: "btn btn-quiet demo-login" },
      el("span", { className: "demo-role", text: ROLES[account.role] || account.role }),
      el("span", { className: "demo-email", text: account.email }),
    );
    button.addEventListener("click", () => logIn(account.email, account.password, button));
    list.append(button);
  }
  $("#demo").hidden = false;
}

init();
