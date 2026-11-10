import { api } from "./api.js";
import { $, busy, clear, dialog, el, emptyRow, field, fillSelect, pill, row, setMessage } from "./dom.js";
import { ROLES, startPage } from "./layout.js";

const ROLE_OPTIONS = Object.entries(ROLES).map(([value, label]) => ({ value, label }));

async function init() {
  const me = await startPage({ roles: ["admin"] });
  if (!me) return;

  const createForm = $("#create-form");
  const createMessage = $("#create-message");
  const rows = $("#rows");
  const message = $("#message");
  const editForm = $("#edit-form");
  const editMessage = $("#edit-message");
  const editDialog = dialog($("#edit-dialog"));
  let editing = null;

  fillSelect(field(createForm, "role"), ROLE_OPTIONS);
  field(createForm, "role").value = "worker";
  fillSelect(field(editForm, "role"), ROLE_OPTIONS);

  function openEdit(user) {
    editing = user;
    const self = user.id === me.id;
    $("#edit-title").textContent = self ? "Edit your account" : `Edit ${user.name}`;
    field(editForm, "name").value = user.name;
    field(editForm, "role").value = user.role;
    field(editForm, "is_active").checked = user.is_active;
    field(editForm, "password").value = "";
    // The API refuses to let you demote or deactivate yourself; make that visible here too.
    field(editForm, "role").disabled = self;
    field(editForm, "is_active").disabled = self;
    setMessage(editMessage, self ? "You cannot change your own role or deactivate yourself." : "", "info");
    editDialog.open();
  }

  async function load() {
    try {
      const users = await api("/users");
      setMessage(message, "");
      clear(rows);
      if (users.length === 0) rows.append(emptyRow(5, "No users."));
      for (const u of users) {
        const edit = el("button", { type: "button", className: "btn btn-quiet btn-small", text: "Edit" });
        edit.addEventListener("click", () => openEdit(u));
        rows.append(
          row(
            [
              u.id === me.id ? `${u.name} (you)` : u.name,
              u.email,
              ROLES[u.role] || u.role,
              u.is_active ? pill("Active", "ok") : pill("Inactive"),
              edit,
            ],
            u.is_active ? undefined : "is-inactive",
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
      name: field(createForm, "name").value.trim(),
      email: field(createForm, "email").value.trim(),
      password: field(createForm, "password").value,
      role: field(createForm, "role").value,
    };
    const problems = [];
    if (!body.name) problems.push("Name is required.");
    if (!body.email.includes("@")) problems.push("Enter a valid email address.");
    if (body.password.length < 8) problems.push("Password must be at least 8 characters.");
    if (problems.length) {
      setMessage(createMessage, problems.join("\n"));
      return;
    }
    await busy(createForm.querySelector('button[type="submit"]'), async () => {
      try {
        const created = await api("/users", { method: "POST", body });
        setMessage(createMessage, `Added ${created.name} as ${ROLES[created.role]}.`, "ok");
        createForm.reset();
        field(createForm, "role").value = "worker";
        await load();
      } catch (error) {
        setMessage(createMessage, error.message);
      }
    });
  });

  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = { name: field(editForm, "name").value.trim() };
    if (editing.id !== me.id) {
      body.role = field(editForm, "role").value;
      body.is_active = field(editForm, "is_active").checked;
    }
    const password = field(editForm, "password").value;
    if (password) body.password = password;
    if (!body.name) {
      setMessage(editMessage, "Name is required.");
      return;
    }
    if (password && password.length < 8) {
      setMessage(editMessage, "New password must be at least 8 characters.");
      return;
    }
    await busy(editForm.querySelector('button[type="submit"]'), async () => {
      try {
        await api(`/users/${editing.id}`, { method: "PATCH", body });
        editDialog.close();
        setMessage(message, `Saved ${body.name}.`, "ok");
        await load();
      } catch (error) {
        setMessage(editMessage, error.message);
      }
    });
  });

  load();
}

init();
