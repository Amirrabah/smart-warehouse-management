import { api, ApiError, clearToken, getToken, setToken } from "./api.js";
import { $, busy, queryParam, setMessage } from "./dom.js";
import { homeFor } from "./layout.js";

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

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = form.email.value.trim();
    const password = form.password.value;
    if (!email || !password) {
      setMessage(message, "Enter your email and password.");
      return;
    }
    await busy(form.querySelector("button"), async () => {
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
  });
  form.email.focus();
}

init();
