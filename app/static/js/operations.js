import { api } from "./api.js";
import { $, busy, clear, emptyRow, fillSelect, fmtQty, queryParam, setMessage } from "./dom.js";
import { startPage } from "./layout.js";
import { loadLocations, loadProducts, movementRow, productOptions } from "./lookups.js";

const TYPES = {
  receive: {
    button: "Receive stock",
    help: "Goods arrive: add stock to a location.",
  },
  pick: {
    button: "Pick stock",
    help: "Goods leave for an order: take stock from a location.",
  },
  move: {
    button: "Move stock",
    help: "Move stock from one location to another. The total does not change.",
  },
  adjust: {
    button: "Save adjustment",
    help: "Correct the quantity after a count. A reason is required.",
  },
};

async function init() {
  const user = await startPage({ roles: ["admin", "worker"] });
  if (!user) return;

  const form = $("#op-form");
  const message = $("#message");
  let products;
  let locations;
  let stockByLocation = new Map(); // location id -> quantity of the selected product

  try {
    [products, locations] = await Promise.all([
      loadProducts({ active: true }),
      loadLocations(),
    ]);
  } catch (error) {
    setMessage(message, error.message);
    return;
  }
  const activeLocations = [...locations.values()].filter((l) => l.is_active);

  fillSelect(form.product, productOptions(products), { placeholder: "Choose a product" });

  const type = () => form.querySelector('input[name="type"]:checked').value;
  const product = () => products.get(Number(form.product.value));

  function showFields() {
    const current = type();
    for (const field of form.querySelectorAll("[data-for]")) {
      field.hidden = !field.dataset.for.split(" ").includes(current);
    }
    $("#submit").textContent = TYPES[current].button;
    $("#type-help").textContent = TYPES[current].help;
    const required = current === "adjust";
    form.reason.required = required;
    $("#reason-label").textContent = required ? "Reason (required)" : "Reason (optional)";
    fillLocations();
  }

  function qtyLabel(locationId) {
    const p = product();
    const qty = stockByLocation.get(locationId) || 0;
    return p ? fmtQty(qty, p.unit) : String(qty);
  }

  function fillLocations() {
    const held = activeLocations.filter((l) => (stockByLocation.get(l.id) || 0) > 0);
    // Stock can sit on a shelf that was deactivated earlier; it can still be picked or moved away.
    for (const [id, qty] of stockByLocation) {
      const location = locations.get(id);
      if (qty > 0 && location && !location.is_active) held.push(location);
    }
    fillSelect(
      form.from,
      held.map((l) => ({ value: l.id, label: `${l.code} (${qtyLabel(l.id)})` })),
      { placeholder: product() ? (held.length ? "Choose a location" : "No stock anywhere") : "Choose a product first" },
    );
    const fromId = Number(form.from.value);
    fillSelect(
      form.to,
      activeLocations
        .filter((l) => !(type() === "move" && l.id === fromId))
        .map((l) => ({ value: l.id, label: l.code })),
      { placeholder: "Choose a location" },
    );
    fillSelect(
      form.at,
      activeLocations.map((l) => ({ value: l.id, label: `${l.code} (${qtyLabel(l.id)})` })),
      { placeholder: "Choose a location" },
    );
    const p = product();
    $("#unit-hint").textContent = p ? `Unit: ${p.unit}` : "";
  }

  async function loadProductStock() {
    stockByLocation = new Map();
    const p = product();
    if (p) {
      try {
        const stock = await api(`/stock/${p.id}`);
        stockByLocation = new Map(stock.locations.map((l) => [l.location_id, l.quantity]));
      } catch (error) {
        setMessage(message, error.message);
      }
    }
    fillLocations();
  }

  async function loadRecent() {
    const body = clear($("#recent"));
    try {
      const page = await api("/movements", { params: { user_id: user.id, limit: 5 } });
      if (page.items.length === 0) body.append(emptyRow(7, "You have not recorded any movements yet."));
      for (const m of page.items) {
        body.append(movementRow(m, { locations, products, me: user, showUser: false }));
      }
    } catch {
      body.append(emptyRow(7, "Could not load your recent movements."));
    }
  }

  function buildRequest() {
    const current = type();
    const p = product();
    const quantity = Number(form.quantity.value);
    const reason = form.reason.value.trim();
    const problems = [];
    if (!p) problems.push("Choose a product.");
    if (!Number.isInteger(quantity) || quantity <= 0) problems.push("Quantity must be a whole number above 0.");
    if ((current === "pick" || current === "move") && !form.from.value) problems.push("Choose the location to take stock from.");
    if ((current === "receive" || current === "move") && !form.to.value) problems.push("Choose the location to put stock in.");
    if (current === "adjust" && !form.at.value) problems.push("Choose the location you counted.");
    if (current === "adjust" && !reason) problems.push("Write why the count is different.");
    if (problems.length) return { problems };

    const base = { product_id: p.id };
    if (reason) base.reason = reason;
    switch (current) {
      case "receive":
        return { body: { ...base, to_location_id: Number(form.to.value), quantity } };
      case "pick":
        return { body: { ...base, from_location_id: Number(form.from.value), quantity } };
      case "move":
        return {
          body: {
            ...base,
            from_location_id: Number(form.from.value),
            to_location_id: Number(form.to.value),
            quantity,
          },
        };
      default:
        return {
          body: {
            ...base,
            location_id: Number(form.at.value),
            quantity_change: Number(form.direction.value) * quantity,
          },
        };
    }
  }

  function successText(current, body, result) {
    const p = product();
    const code = (id) => locations.get(id)?.code ?? `#${id}`;
    const after = result.inventory
      .map((level) => `${code(level.location_id)} now holds ${fmtQty(level.quantity, p.unit)}.`)
      .join(" ");
    const qty = fmtQty(result.movement.quantity, p.unit);
    const what = {
      receive: `Received ${qty} of ${p.sku} into ${code(body.to_location_id)}.`,
      pick: `Picked ${qty} of ${p.sku} from ${code(body.from_location_id)}.`,
      move: `Moved ${qty} of ${p.sku} from ${code(body.from_location_id)} to ${code(body.to_location_id)}.`,
      adjust: `Adjusted ${p.sku} at ${code(body.location_id)} by ${body.quantity_change > 0 ? "+" : "-"}${qty}.`,
    }[current];
    return `${what} ${after}`;
  }

  form.addEventListener("change", (event) => {
    if (event.target.name === "type") {
      setMessage(message, "");
      showFields();
    } else if (event.target === form.product) {
      loadProductStock();
    } else if (event.target === form.from) {
      fillLocations();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const current = type();
    const request = buildRequest();
    if (request.problems) {
      setMessage(message, request.problems.join("\n"));
      return;
    }
    await busy($("#submit"), async () => {
      try {
        const result = await api(`/movements/${current}`, { method: "POST", body: request.body });
        setMessage(message, successText(current, request.body, result), "ok");
        form.quantity.value = "";
        form.reason.value = "";
        await Promise.all([loadProductStock(), loadRecent()]);
      } catch (error) {
        setMessage(message, error.message);
      }
    });
  });

  // Prefill from links such as operations.html?type=pick&product=3&from=7
  const startType = queryParam("type");
  if (TYPES[startType]) form.querySelector(`#type-${startType}`).checked = true;
  const startProduct = queryParam("product");
  if (startProduct && products.has(Number(startProduct))) form.product.value = startProduct;
  showFields();
  await loadProductStock();
  const startFrom = queryParam("from");
  if (startFrom) {
    if (type() === "adjust") form.at.value = startFrom;
    else form.from.value = startFrom;
    fillLocations();
  }
  loadRecent();
}

init();
