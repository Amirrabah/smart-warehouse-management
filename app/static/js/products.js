import { api } from "./api.js";
import {
  $,
  busy,
  clear,
  debounce,
  dialog,
  el,
  emptyRow,
  field,
  fillSelect,
  fmtNumber,
  pill,
  row,
  setMessage,
} from "./dom.js";
import { startPage } from "./layout.js";
import { UNITS } from "./lookups.js";

async function init() {
  const user = await startPage({ roles: ["admin"] });
  if (!user) return;

  const createForm = $("#create-form");
  const createMessage = $("#create-message");
  const filters = $("#filters");
  const rows = $("#rows");
  const message = $("#message");
  const editForm = $("#edit-form");
  const editMessage = $("#edit-message");
  const editDialog = dialog($("#edit-dialog"));
  let editing = null;

  fillSelect(field(createForm, "unit"), UNITS.map((u) => ({ value: u, label: u })));

  function openEdit(product) {
    editing = product;
    $("#edit-title").textContent = `Edit ${product.sku}`;
    field(editForm, "name").value = product.name;
    field(editForm, "reorder_point").value = product.reorder_point;
    field(editForm, "is_active").checked = product.is_active;
    setMessage(editMessage, "");
    editDialog.open();
  }

  async function load() {
    try {
      const products = await api("/products", {
        params: { search: field(filters, "search").value.trim(), active: field(filters, "active").value },
      });
      setMessage(message, "");
      clear(rows);
      if (products.length === 0) rows.append(emptyRow(6, "No products match."));
      for (const p of products) {
        const edit = el("button", { type: "button", className: "btn btn-quiet btn-small", text: "Edit" });
        edit.addEventListener("click", () => openEdit(p));
        rows.append(
          row(
            [
              el("a", { className: "sku", href: `product.html?id=${p.id}`, text: p.sku }),
              p.name,
              p.unit,
              { content: fmtNumber(p.reorder_point), className: "num" },
              p.is_active ? pill("Active", "ok") : pill("Inactive"),
              edit,
            ],
            p.is_active ? undefined : "is-inactive",
          ),
        );
      }
    } catch (error) {
      setMessage(message, error.message);
    }
  }

  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      sku: field(createForm, "sku").value.trim().toUpperCase(),
      name: field(createForm, "name").value.trim(),
      unit: field(createForm, "unit").value,
      reorder_point: Number(field(createForm, "reorder_point").value || 0),
    };
    if (!body.sku || !body.name) {
      setMessage(createMessage, "SKU and name are required.");
      return;
    }
    await busy(createForm.querySelector('button[type="submit"]'), async () => {
      try {
        const created = await api("/products", { method: "POST", body });
        setMessage(createMessage, `Added ${created.sku}.`, "ok");
        createForm.reset();
        await load();
      } catch (error) {
        setMessage(createMessage, error.message);
      }
    });
  });

  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = field(editForm, "name").value.trim();
    const reorderPoint = Number(field(editForm, "reorder_point").value);
    const isActive = field(editForm, "is_active").checked;
    if (!name) {
      setMessage(editMessage, "Name is required.");
      return;
    }
    if (!Number.isInteger(reorderPoint) || reorderPoint < 0) {
      setMessage(editMessage, "Reorder point must be a whole number, 0 or more.");
      return;
    }
    await busy(editForm.querySelector('button[type="submit"]'), async () => {
      try {
        await api(`/products/${editing.id}`, { method: "PATCH", body: { name, is_active: isActive } });
        if (reorderPoint !== editing.reorder_point) {
          await api(`/products/${editing.id}/reorder-point`, {
            method: "PATCH",
            body: { reorder_point: reorderPoint },
          });
        }
        editDialog.close();
        setMessage(message, `Saved ${editing.sku}.`, "ok");
        await load();
      } catch (error) {
        setMessage(editMessage, error.message);
      }
    });
  });

  filters.addEventListener("submit", (event) => event.preventDefault());
  field(filters, "search").addEventListener("input", debounce(load));
  field(filters, "active").addEventListener("change", load);
  load();
}

init();
