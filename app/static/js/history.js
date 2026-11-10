import { api } from "./api.js";
import { $, clear, createPager, emptyRow, fillSelect, queryParam, setMessage } from "./dom.js";
import { startPage } from "./layout.js";
import {
  loadLocations,
  loadProducts,
  loadUsers,
  locationOptions,
  MOVEMENT_TYPES,
  movementRow,
  productOptions,
} from "./lookups.js";

const LIMIT = 50;
const FILTERS = ["product_id", "location_id", "type", "user_id", "date_from", "date_to"];

async function init() {
  const user = await startPage();
  if (!user) return;

  const form = $("#filters");
  const rows = $("#rows");
  const message = $("#message");
  let products;
  let locations;
  let users;
  try {
    [products, locations, users] = await Promise.all([loadProducts(), loadLocations(), loadUsers(user)]);
  } catch (error) {
    setMessage(message, error.message);
    return;
  }

  fillSelect(form.product_id, productOptions(products), { placeholder: "All products" });
  fillSelect(form.location_id, locationOptions(locations), { placeholder: "All locations" });
  fillSelect(
    form.type,
    Object.entries(MOVEMENT_TYPES).map(([value, label]) => ({ value, label })),
    { placeholder: "All types" },
  );
  if (users.size) {
    $("#user-field").hidden = false;
    fillSelect(
      form.user_id,
      [...users.values()].map((u) => ({ value: u.id, label: u.name })),
      { placeholder: "All users" },
    );
  }

  // Filters can come from links, e.g. history.html?product_id=4
  for (const name of FILTERS) {
    const value = queryParam(name);
    if (value) form[name].value = value;
  }

  const updatePager = createPager($("#pager"), LIMIT, load);

  function filters() {
    const params = {};
    for (const name of FILTERS) params[name] = form[name].value;
    return params;
  }

  async function load(offset = 0) {
    const params = filters();
    const shown = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    window.history.replaceState(null, "", shown.toString() ? `?${shown}` : window.location.pathname);
    try {
      const page = await api("/movements", { params: { ...params, limit: LIMIT, offset } });
      setMessage(message, "");
      clear(rows);
      if (page.items.length === 0) rows.append(emptyRow(8, "No movements match these filters."));
      for (const m of page.items) rows.append(movementRow(m, { locations, products, users, me: user }));
      updatePager(offset, page.total, page.items.length);
    } catch (error) {
      setMessage(message, error.message);
    }
  }

  form.addEventListener("change", () => load(0));
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("reset", () => setTimeout(() => load(0)));
  load(0);
}

init();
