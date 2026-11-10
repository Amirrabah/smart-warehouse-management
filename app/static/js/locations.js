import { api } from "./api.js";
import { $, busy, clear, dialog, el, emptyRow, field, locTag, pill, row, setMessage } from "./dom.js";
import { startPage } from "./layout.js";

const CODE_PATTERN = /^[A-Z]-\d{2}-\d{2}$/;

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

  function openEdit(location) {
    editing = location;
    $("#edit-title").textContent = `Edit ${location.code}`;
    field(editForm, "description").value = location.description || "";
    field(editForm, "is_active").checked = location.is_active;
    setMessage(editMessage, "");
    editDialog.open();
  }

  async function load() {
    try {
      const locations = await api("/locations", { params: { active: field(filters, "active").value } });
      setMessage(message, "");
      clear(rows);
      if (locations.length === 0) rows.append(emptyRow(4, "No locations yet. Add the first one above."));
      for (const l of locations) {
        const edit = el("button", { type: "button", className: "btn btn-quiet btn-small", text: "Edit" });
        edit.addEventListener("click", () => openEdit(l));
        rows.append(
          row(
            [
              locTag(l.code, l.id, { active: l.is_active }),
              l.description || el("span", { className: "muted", text: "-" }),
              l.is_active ? pill("Active", "ok") : pill("Inactive"),
              edit,
            ],
            l.is_active ? undefined : "is-inactive",
          ),
        );
      }
    } catch (error) {
      setMessage(message, error.message);
    }
  }

  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = field(createForm, "code").value.trim().toUpperCase();
    const description = field(createForm, "description").value.trim();
    if (!CODE_PATTERN.test(code)) {
      setMessage(createMessage, "Use the code format A-01-03: one letter, two digits, two digits.");
      return;
    }
    await busy(createForm.querySelector('button[type="submit"]'), async () => {
      try {
        const created = await api("/locations", {
          method: "POST",
          body: description ? { code, description } : { code },
        });
        setMessage(createMessage, `Added ${created.code}.`, "ok");
        createForm.reset();
        await load();
      } catch (error) {
        setMessage(createMessage, error.message);
      }
    });
  });

  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      description: field(editForm, "description").value.trim(),
      is_active: field(editForm, "is_active").checked,
    };
    await busy(editForm.querySelector('button[type="submit"]'), async () => {
      try {
        await api(`/locations/${editing.id}`, { method: "PATCH", body });
        editDialog.close();
        setMessage(message, `Saved ${editing.code}.`, "ok");
        await load();
      } catch (error) {
        const hint = error.status === 409 ? "\nMove or pick its stock first, then deactivate it." : "";
        setMessage(editMessage, error.message + hint);
      }
    });
  });

  filters.addEventListener("submit", (event) => event.preventDefault());
  field(filters, "active").addEventListener("change", load);
  load();
}

init();
