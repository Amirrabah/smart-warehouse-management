// Small DOM helpers. Text only ever goes in through textContent / text nodes,
// so data from the API can never be read as HTML.

/**
 * el("a", { className: "loc", href: "shelf.html?id=3", text: "A-01-03" })
 * Props: className, text, dataset, on: { click: fn }, plus any attribute (set with setAttribute).
 * Children: nodes, strings (become text nodes), or null/false (skipped).
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = String(value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "on") {
      for (const [event, handler] of Object.entries(value)) node.addEventListener(event, handler);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function $(selector, root = document) {
  return root.querySelector(selector);
}

/** A form control by name. Safer than form.name, which is the form's own name attribute. */
export function field(form, name) {
  return form.elements.namedItem(name);
}

/** Wire a <dialog>: buttons with data-close close it. Returns { open, close }. */
export function dialog(node) {
  for (const button of node.querySelectorAll("[data-close]")) {
    button.addEventListener("click", () => node.close());
  }
  return { open: () => node.showModal(), close: () => node.close() };
}

/** Show a message box: kind is "error", "ok" or "info". Empty text hides it. */
export function setMessage(box, text, kind = "error") {
  box.textContent = text || "";
  box.className = `msg msg-${kind}`;
  box.hidden = !text;
  if (text && kind === "error") box.setAttribute("role", "alert");
  else box.setAttribute("role", "status");
}

export function locTag(code, locationId, { active = true } = {}) {
  const className = active ? "loc" : "loc loc-off";
  if (locationId === undefined || locationId === null) return el("span", { className, text: code });
  return el("a", { className, href: `shelf.html?id=${encodeURIComponent(locationId)}`, text: code });
}

export function pill(text, kind) {
  return el("span", { className: kind ? `pill pill-${kind}` : "pill", text });
}

export function stockStatus(belowReorder) {
  return belowReorder ? pill("Below reorder point", "alert") : pill("OK", "ok");
}

const numberFormat = new Intl.NumberFormat("en-GB");
const decimalFormat = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function fmtNumber(value) {
  return numberFormat.format(value);
}

export function fmtDecimal(value) {
  return decimalFormat.format(value);
}

export function fmtQty(value, unit) {
  return `${numberFormat.format(value)} ${unit}`;
}

export function fmtDateTime(iso) {
  return iso ? dateTimeFormat.format(new Date(iso)) : "";
}

/** A table row from a list of cells. A cell is a node, a string, or { content, className }. */
export function row(cells, className) {
  return el(
    "tr",
    { className },
    cells.map((cell) => {
      if (cell && typeof cell === "object" && !(cell instanceof Node) && "content" in cell) {
        return el("td", { className: cell.className }, cell.content);
      }
      return el("td", {}, cell);
    }),
  );
}

export function emptyRow(colspan, text) {
  return el("tr", {}, el("td", { className: "empty", colspan, text }));
}

/** Fill a <select> with options. items: [{ value, label }]. Keeps the current value if possible. */
export function fillSelect(select, items, { placeholder, keep = true } = {}) {
  const previous = select.value;
  clear(select);
  if (placeholder !== undefined) select.append(el("option", { value: "", text: placeholder }));
  for (const item of items) select.append(el("option", { value: item.value, text: item.label }));
  if (keep && [...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
}

export function debounce(fn, wait = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function queryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

/**
 * Pager for { items, total } lists. Calls load(offset) when a button is pressed.
 * Returns update(offset, total, shown).
 */
export function createPager(container, limit, load) {
  const info = el("span");
  const prev = el("button", { type: "button", className: "btn btn-quiet btn-small", text: "Previous" });
  const next = el("button", { type: "button", className: "btn btn-quiet btn-small", text: "Next" });
  let offset = 0;
  prev.addEventListener("click", () => load(Math.max(0, offset - limit)));
  next.addEventListener("click", () => load(offset + limit));
  clear(container).append(info, el("div", { className: "actions" }, prev, next));

  return function update(newOffset, total, shown) {
    offset = newOffset;
    info.textContent = total === 0 ? "" : `Showing ${fmtNumber(offset + 1)}–${fmtNumber(offset + shown)} of ${fmtNumber(total)}`;
    prev.disabled = offset === 0;
    next.disabled = offset + shown >= total;
    container.hidden = total <= limit && offset === 0;
  };
}

/** Disable a form's submit button while a request runs. */
export async function busy(button, task) {
  button.disabled = true;
  try {
    return await task();
  } finally {
    button.disabled = false;
  }
}
