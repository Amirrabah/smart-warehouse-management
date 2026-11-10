import { api } from "./api.js";
import {
  $,
  busy,
  clear,
  el,
  emptyRow,
  fmtNumber,
  fmtQty,
  locTag,
  queryParam,
  row,
  setMessage,
  stockStatus,
} from "./dom.js";
import { can, startPage } from "./layout.js";
import { loadLocations, movementRow } from "./lookups.js";

function fact(label, value) {
  return el("div", {}, el("dt", { text: label }), el("dd", {}, value));
}

async function init() {
  const user = await startPage();
  if (!user) return;

  const message = $("#message");
  const id = Number(queryParam("id"));
  if (!Number.isInteger(id) || id <= 0) {
    setMessage(message, "No product selected. Open a product from the stock overview.");
    return;
  }

  let product;
  let stock;
  let locations;
  try {
    [product, stock, locations] = await Promise.all([
      api(`/products/${id}`),
      api(`/stock/${id}`),
      loadLocations(),
    ]);
  } catch (error) {
    setMessage(message, error.message);
    return;
  }

  document.title = `${product.sku} | Smart Warehouse`;
  $("#title").textContent = product.name;
  $("#subtitle").textContent = product.is_active ? product.sku : `${product.sku} (inactive)`;
  $("#history-link").href = `history.html?product_id=${id}`;

  function renderFacts() {
    clear($("#facts")).append(
      fact("In stock", fmtQty(stock.total, stock.unit)),
      fact("Reorder point", fmtNumber(stock.reorder_point)),
      fact("Status", stockStatus(stock.below_reorder)),
    );
  }
  renderFacts();

  const actions = $("#actions");
  if (can.operate(user) && product.is_active) {
    actions.append(
      el("a", { className: "btn", href: `operations.html?type=receive&product=${id}`, text: "Receive" }),
      el("a", { className: "btn btn-quiet", href: `operations.html?type=pick&product=${id}`, text: "Pick" }),
    );
  }

  const locationRows = $("#locations");
  if (stock.locations.length === 0) {
    locationRows.append(emptyRow(3, "Not stored anywhere right now."));
  }
  for (const item of stock.locations) {
    const active = locations.get(item.location_id)?.is_active ?? true;
    const links = el("div", { className: "actions" });
    if (can.operate(user) && product.is_active) {
      for (const [type, text] of [["pick", "Pick"], ["move", "Move"], ["adjust", "Adjust"]]) {
        links.append(
          el("a", {
            className: "btn btn-quiet btn-small",
            href: `operations.html?type=${type}&product=${id}&from=${item.location_id}`,
            text,
          }),
        );
      }
    }
    locationRows.append(
      row([
        locTag(item.code, item.location_id, { active }),
        { content: fmtQty(item.quantity, stock.unit), className: "num" },
        links,
      ]),
    );
  }

  const reorderForm = $("#reorder-form");
  if (can.setReorderPoint(user)) {
    reorderForm.hidden = false;
    reorderForm.reorder_point.value = stock.reorder_point;
    const reorderMessage = $("#reorder-message");
    reorderForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const value = Number(reorderForm.reorder_point.value);
      if (!Number.isInteger(value) || value < 0) {
        setMessage(reorderMessage, "Enter a whole number, 0 or more.");
        return;
      }
      await busy(reorderForm.querySelector("button"), async () => {
        try {
          const updated = await api(`/products/${id}/reorder-point`, {
            method: "PATCH",
            body: { reorder_point: value },
          });
          stock.reorder_point = updated.reorder_point;
          stock.below_reorder = stock.total < updated.reorder_point;
          renderFacts();
          setMessage(reorderMessage, `Reorder point saved: ${fmtNumber(updated.reorder_point)}.`, "ok");
        } catch (error) {
          setMessage(reorderMessage, error.message);
        }
      });
    });
  }

  try {
    const page = await api("/movements", { params: { product_id: id, limit: 10 } });
    const body = $("#movements");
    if (page.items.length === 0) body.append(emptyRow(6, "No movements yet."));
    const products = new Map([[id, product]]);
    for (const m of page.items) {
      body.append(movementRow(m, { locations, products, me: user, showProduct: false, showUser: false }));
    }
  } catch (error) {
    setMessage(message, error.message);
  }
}

init();
