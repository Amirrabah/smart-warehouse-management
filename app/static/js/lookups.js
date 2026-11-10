// Lists that pages use to turn ids into SKUs, location codes and names.

import { api } from "./api.js";
import { el, fmtDateTime, fmtNumber, locTag, pill, row } from "./dom.js";

export const MOVEMENT_TYPES = {
  receive: "Receive",
  pick: "Pick",
  move: "Move",
  adjust: "Adjust",
};

export const UNITS = ["pcs", "box", "kg"];

function byId(items) {
  return new Map(items.map((item) => [item.id, item]));
}

export async function loadLocations(params = {}) {
  return byId(await api("/locations", { params }));
}

export async function loadProducts(params = {}) {
  return byId(await api("/products", { params }));
}

/** Only admins can list users. Everyone else gets an empty map and sees "User #id". */
export async function loadUsers(user) {
  if (user.role !== "admin") return new Map();
  return byId(await api("/users"));
}

export function productOptions(products) {
  return [...products.values()].map((p) => ({ value: p.id, label: `${p.sku} | ${p.name}` }));
}

export function locationOptions(locations) {
  return [...locations.values()].map((l) => ({
    value: l.id,
    label: l.description ? `${l.code} | ${l.description}` : l.code,
  }));
}

function locCell(locations, id) {
  if (id === null || id === undefined) return el("span", { className: "muted", text: "-" });
  const location = locations.get(id);
  return locTag(location ? location.code : `#${id}`, id, { active: location ? location.is_active : true });
}

function userName(users, me, id) {
  if (me && id === me.id) return "You";
  const found = users.get(id);
  return found ? found.name : `User #${id}`;
}

/** One movement as a table row. Signed quantity: + for stock in, - for stock out. */
export function movementRow(m, { locations, products, users = new Map(), me, showProduct = true, showUser = true }) {
  let sign = "";
  if (m.type === "receive" || (m.type === "adjust" && m.to_location_id !== null)) sign = "+";
  if (m.type === "pick" || (m.type === "adjust" && m.from_location_id !== null)) sign = "-";

  const product = products ? products.get(m.product_id) : null;
  const cells = [
    { content: fmtDateTime(m.created_at), className: "nowrap" },
    pill(MOVEMENT_TYPES[m.type] || m.type, m.type),
  ];
  if (showProduct) {
    cells.push(
      el("a", {
        className: "sku",
        href: `product.html?id=${m.product_id}`,
        text: product ? product.sku : `#${m.product_id}`,
      }),
    );
  }
  cells.push(
    locCell(locations, m.from_location_id),
    locCell(locations, m.to_location_id),
    { content: `${sign}${fmtNumber(m.quantity)}${product ? ` ${product.unit}` : ""}`, className: "num" },
  );
  if (showUser) cells.push(userName(users, me, m.user_id));
  cells.push(m.reason || el("span", { className: "muted", text: "-" }));
  return row(cells);
}
