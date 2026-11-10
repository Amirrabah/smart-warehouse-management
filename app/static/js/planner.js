import { api } from "./api.js";
import {
  $,
  clear,
  createPager,
  el,
  emptyRow,
  fmtDecimal,
  fmtNumber,
  fmtQty,
  row,
  setMessage,
  stockStatus,
} from "./dom.js";
import { startPage } from "./layout.js";

const LIMIT = 50;
const GAUGE_DAYS = 60; // a full bar = two months of stock or more

function daysLeftCell(days) {
  if (days === null) return { content: el("span", { className: "muted", text: "-" }), className: "num" };
  const step = Math.max(0, Math.min(10, Math.round((days / GAUGE_DAYS) * 10)));
  let level = "";
  if (days < 7) level = " is-low";
  else if (days < 21) level = " is-mid";
  const gauge = el(
    "span",
    { className: "gauge" },
    el("span", { text: fmtDecimal(days) }),
    el(
      "span",
      { className: "gauge-track", "aria-hidden": "true" },
      el("span", { className: `gauge-fill w-${step}${level}` }),
    ),
  );
  return { content: gauge, className: "num" };
}

async function init() {
  const user = await startPage();
  if (!user) return;

  const form = $("#filters");
  const rows = $("#rows");
  const message = $("#message");
  const updatePager = createPager($("#pager"), LIMIT, load);

  async function load(offset = 0) {
    try {
      const page = await api("/planner", {
        params: {
          sort: form.sort.value,
          only_below: form.only_below.checked ? true : undefined,
          limit: LIMIT,
          offset,
        },
      });
      setMessage(message, "");
      clear(rows);
      if (page.items.length === 0) {
        rows.append(
          emptyRow(8, form.only_below.checked ? "Nothing is below its reorder point." : "No active products yet."),
        );
      }
      for (const item of page.items) {
        rows.append(
          row(
            [
              el("a", { className: "sku", href: `product.html?id=${item.product_id}`, text: item.sku }),
              item.name,
              { content: fmtQty(item.total, item.unit), className: "num" },
              { content: fmtNumber(item.reorder_point), className: "num" },
              { content: fmtNumber(item.used_last_30_days), className: "num" },
              { content: fmtDecimal(item.avg_daily_usage), className: "num" },
              daysLeftCell(item.days_left),
              stockStatus(item.below_reorder),
            ],
            item.below_reorder ? "is-below" : undefined,
          ),
        );
      }
      updatePager(offset, page.total, page.items.length);
    } catch (error) {
      setMessage(message, error.message);
    }
  }

  form.addEventListener("change", () => load(0));
  form.addEventListener("submit", (event) => event.preventDefault());
  load(0);
}

init();
