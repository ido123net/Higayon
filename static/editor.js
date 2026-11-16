import {
  api,
  date,
  key
} from "./api.js";
const $ = id => document.getElementById(id);
let current = null,
  slots = [],
  dirty = false,
  busy = false;

function setBusy(value) {
  busy = value;
  $("editor").setAttribute("aria-busy", String(value));
  for (const control of document.querySelectorAll("#editor input, #editor textarea, #editor button, #puzzles, #new")) {
    control.disabled = value;
  }
}
// The fixed template is provided by the same authenticated API even before any puzzle exists.
async function init() {
  try {
    const template = await fetch("/api/v1/template/", {
      credentials: "same-origin"
    });
    if (!template.ok) throw new Error();
    slots = (await template.json()).slots;
  } catch {
    throw new Error("לא ניתן לטעון את תבנית התשבץ. יש לרענן ולנסות שוב.");
  }
  build();
  await list();
}
async function list() {
  const data = await api();
  $("puzzles").replaceChildren(new Option("תשבץ חדש", ""));
  for (const p of data.puzzles) $("puzzles").add(new Option(`${p.title} · נוסף ${date(p.created_at)}`, p.id));
  $("puzzles").value = current || "";
}

function build(clues = []) {
  $("fields").replaceChildren();
  for (const d of ["across", "down"]) {
    const fieldset = document.createElement("fieldset"),
      legend = document.createElement("legend");
    legend.textContent = d === "across" ? "מאוזן" : "מאונך";
    fieldset.append(legend);
    for (const s of slots.filter(s => s.direction === d)) {
      const c = clues.find(c => key(c) === key(s)),
        label = document.createElement("label"),
        text = document.createElement("textarea"),
        groups = document.createElement("input"),
        gl = document.createElement("label");
      label.textContent = `${s.number} · ${s.length} אותיות`;
      text.id = key(s);
      text.value = c?.text || "";
      text.required = true;
      text.disabled = busy;
      text.maxLength = 5000;
      label.append(text);
      gl.textContent = "קבוצות אורך (רשות, מופרדות בפסיקים)";
      groups.id = `groups-${key(s)}`;
      groups.dir = "ltr";
      groups.disabled = busy;
      groups.value = c?.enumeration?.join(", ") || "";
      gl.append(groups);
      fieldset.append(label, gl);
    }
    $("fields").append(fieldset);
  }
}
$("editor").addEventListener("input", () => {
  dirty = true;
});
async function choose(id) {
  if (busy) return;
  if (dirty && !confirm("לעבור לתשבץ אחר ולוותר על השינויים שלא נשמרו?")) {
    $("puzzles").value = current || "";
    return;
  }
  setBusy(true);
  $("status").textContent = "טוען תשבץ…";
  try {
    const p = id ? await api(`${id}/`) : null;
    current = p?.id || null;
    $("title").value = p?.title || "";
    build(p?.clues);
    dirty = false;
    $("status").textContent = "";
    $("puzzles").value = current || "";
  } catch (e) {
    $("status").textContent = e.message;
    $("puzzles").value = current || "";
  } finally {
    setBusy(false);
  }
}
$("new").addEventListener("click", () => choose(""));
$("puzzles").addEventListener("change", e => choose(e.target.value));
$("editor").addEventListener("submit", async e => {
  e.preventDefault();
  if (busy) return;
  setBusy(true);
  $("status").textContent = "שומר תשבץ…";
  const clues = slots.map(s => ({
    direction: s.direction,
    number: s.number,
    text: $(key(s)).value,
    enumeration: $(`groups-${key(s)}`).value.trim() ? $(`groups-${key(s)}`).value.split(/[,،]/).map(v => Number(v.trim())) : null
  }));
  try {
    const p = await api(current ? `${current}/` : "", {
      method: current ? "PATCH" : "POST",
      body: JSON.stringify({
        title: $("title").value,
        clues
      })
    });
    current = p.id;
    dirty = false;
    await list();
    $("status").textContent = "התשבץ נשמר.";
  } catch (e) {
    $("status").textContent = e.message;
  } finally {
    setBusy(false);
  }
});
window.addEventListener("beforeunload", e => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
setBusy(true);
try {
  await init();
  setBusy(false);
} catch (e) {
  $("status").textContent = e.message;
}
