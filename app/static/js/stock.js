import { api } from "./api.js";
import {
  $,
  clear,
  createPager,
  debounce,
  el,
  emptyRow,
  fmtNumber,
  fmtQty,
  queryParam,
  row,
  setMessage,
  stockStatus,
} from "./dom.js";
import { startPage } from "./layout.js";

const LIMIT = 50;

async function init() {
  const user = await startPage();
  if (!user) return;

  const form = $("#filters");
  const rows = $("#rows");
  const message = $("#message");
  const updatePager = createPager($("#pager"), LIMIT, load);

  form.search.value = queryParam("search") || "";
  form.below.checked = queryParam("below") === "1";

  async function load(offset = 0) {
    try {
      const page = await api("/stock", {
        params: {
          search: form.search.value.trim(),
          below_reorder: form.below.checked ? true : undefined,
          limit: LIMIT,
          offset,
        },
      });
      setMessage(message, "");
      clear(rows);
      if (page.items.length === 0) {
        rows.append(emptyRow(5, form.search.value ? "No products match this search." : "No products yet."));
      }
      for (const item of page.items) {
        rows.append(
          row(
            [
              el("a", { className: "sku", href: `product.html?id=${item.product_id}`, text: item.sku }),
              item.name,
              { content: fmtQty(item.total, item.unit), className: "num" },
              { content: fmtNumber(item.reorder_point), className: "num" },
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

  form.addEventListener("submit", (event) => event.preventDefault());
  form.search.addEventListener("input", debounce(() => load(0)));
  form.below.addEventListener("change", () => load(0));
  load(0);
}

init();
