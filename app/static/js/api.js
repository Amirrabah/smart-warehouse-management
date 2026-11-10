// Talks to the API. One place for the token, the 401 redirect and readable error messages.
// The token lives in sessionStorage: it is gone when the tab closes, and it is never in a cookie,
// so other sites cannot make the browser send it (no CSRF).

const TOKEN_KEY = "swm.token";

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage blocked: nothing to clear.
  }
}

export function goToLogin(reason) {
  clearToken();
  const query = reason ? `?${new URLSearchParams({ reason })}` : "";
  window.location.replace(`/app/${query}`);
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// FastAPI sends either a string or, for 422, a list of {loc, msg}. Turn both into plain text.
export function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = (item.loc || []).filter((part) => part !== "body" && part !== "query");
        const msg = String(item.msg || "Invalid value").replace(/^Value error, /, "");
        return field.length ? `${field.join(".").replaceAll("_", " ")}: ${msg}` : msg;
      })
      .join("\n");
  }
  return "";
}

function messageFor(status, detail) {
  const text = formatDetail(detail);
  switch (status) {
    case 403:
      return "Your role is not allowed to do this.";
    case 404:
      return text || "Not found.";
    case 409:
      return text || "This conflicts with the current stock or data.";
    case 422:
      return text ? `Check the form:\n${text}` : "Check the form and try again.";
    case 429:
      return "Too many login attempts. Wait a minute and try again.";
    default:
      if (status >= 500) return "The server had a problem. Try again in a moment.";
      return text || `Request failed (${status}).`;
  }
}

function buildUrl(path, params) {
  if (!params) return path;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

/**
 * Call the API. Returns the parsed JSON body, or throws ApiError with a message
 * that can be shown to the user as-is.
 */
export async function api(path, { method = "GET", body, params, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(buildUrl(path, params), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }

  let data = null;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) {
    data = await response.json().catch(() => null);
  }

  if (response.status === 401 && auth) {
    goToLogin("expired");
    throw new ApiError(401, "Your session ended. Log in again.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, messageFor(response.status, data && data.detail));
  }
  return data;
}

/** Fetch every page of a paginated list (used for small dropdown sources). */
export async function apiAll(path, params = {}) {
  const limit = 200;
  const items = [];
  for (let offset = 0; ; offset += limit) {
    const page = await api(path, { params: { ...params, limit, offset } });
    items.push(...page.items);
    if (items.length >= page.total || page.items.length === 0) return items;
  }
}
