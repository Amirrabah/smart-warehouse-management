import { api } from "./api.js";
import { $, busy, clear, createPager, el, fmtDateTime, setMessage } from "./dom.js";
import { refreshBadge, startPage } from "./layout.js";

const LIMIT = 20;

async function init() {
  const user = await startPage({ roles: ["admin", "planner"] });
  if (!user) return;

  const form = $("#filters");
  const inbox = $("#inbox");
  const message = $("#message");
  const updatePager = createPager($("#pager"), LIMIT, load);
  let currentOffset = 0;

  function item(note) {
    const unread = note.read_at === null;
    const li = el(
      "li",
      { className: unread ? "note is-unread" : "note" },
      el("h3", { text: note.title }),
      el("span", { className: "note-time", text: fmtDateTime(note.created_at) }),
      el("p", { className: "note-body", text: note.body }),
    );
    if (unread) {
      const button = el("button", { type: "button", className: "btn btn-quiet btn-small", text: "Mark as read" });
      button.addEventListener("click", () =>
        busy(button, async () => {
          try {
            await api(`/notifications/${note.id}/read`, { method: "POST" });
            await Promise.all([load(currentOffset), refreshBadge()]);
          } catch (error) {
            setMessage(message, error.message);
          }
        }),
      );
      li.append(el("div", { className: "actions" }, button));
    } else {
      li.append(el("span", { className: "note-time", text: `Read ${fmtDateTime(note.read_at)}` }));
    }
    return li;
  }

  async function load(offset = 0) {
    try {
      const page = await api("/notifications", {
        params: { unread: form.unread.checked ? true : undefined, limit: LIMIT, offset },
      });
      // Marking the last unread item on a page can leave the page empty: step back.
      if (page.items.length === 0 && offset > 0) return load(Math.max(0, offset - LIMIT));
      currentOffset = offset;
      setMessage(message, "");
      clear(inbox);
      if (page.items.length === 0) {
        inbox.append(
          el("li", {
            className: "empty",
            text: form.unread.checked ? "You're all caught up." : "No notifications yet.",
          }),
        );
      }
      for (const note of page.items) inbox.append(item(note));
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
