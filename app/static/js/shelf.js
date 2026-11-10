import { api } from "./api.js";
import { $, clear, el, emptyRow, fillSelect, fmtQty, queryParam, row, setMessage } from "./dom.js";
import { can, startPage } from "./layout.js";
import { loadLocations } from "./lookups.js";

async function init() {
  const user = await startPage();
  if (!user) return;

  const picker = $("#picker");
  const message = $("#message");
  const sheet = $("#sheet");
  const rows = $("#rows");
  let locations;
  try {
    locations = await loadLocations();
  } catch (error) {
    setMessage(message, error.message);
    return;
  }

  fillSelect(
    picker.location,
    [...locations.values()].map((l) => ({
      value: l.id,
      label: l.is_active ? l.code : `${l.code} (inactive)`,
    })),
    { placeholder: "Choose a location" },
  );

  async function show(id) {
    const location = locations.get(id);
    if (!location) {
      sheet.hidden = true;
      return;
    }
    window.history.replaceState(null, "", `?id=${id}`);
    try {
      const items = await api(`/locations/${id}/stock`);
      setMessage(message, "");
      $("#code").textContent = location.code;
      $("#code").className = location.is_active ? "loc loc-big" : "loc loc-big loc-off";
      $("#description").textContent = [location.description, location.is_active ? "" : "Inactive"]
        .filter(Boolean)
        .join(". ");
      document.title = `${location.code} | Smart Warehouse`;
      clear(rows);
      if (items.length === 0) rows.append(emptyRow(5, "This location is empty."));
      for (const item of items) {
        const actions = el("div", { className: "actions" });
        if (can.operate(user)) {
          actions.append(
            el("a", {
              className: "btn btn-quiet btn-small",
              href: `operations.html?type=adjust&product=${item.product_id}&from=${id}`,
              text: "Record count difference",
            }),
          );
        }
        rows.append(
          row([
            el("a", { className: "sku", href: `product.html?id=${item.product_id}`, text: item.sku }),
            item.name,
            { content: fmtQty(item.quantity, item.unit), className: "num" },
            { content: "", className: "count-col print-only" },
            { content: actions, className: "no-print" },
          ]),
        );
      }
      sheet.hidden = false;
    } catch (error) {
      sheet.hidden = true;
      setMessage(message, error.message);
    }
  }

  picker.addEventListener("submit", (event) => event.preventDefault());
  picker.location.addEventListener("change", () => show(Number(picker.location.value)));
  $("#print").addEventListener("click", () => window.print());

  const start = queryParam("id");
  if (start && locations.has(Number(start))) {
    picker.location.value = start;
    show(Number(start));
  }
}

init();
