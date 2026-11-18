import {sessionApi, sharedSession, completedAnswer} from "./sessions.js";
import {
  api,
  date,
  key,
  enumeration
} from "./api.js";
import {
  letters,
  progress
} from "./storage.js";
import {
  writeWord,
  erase
} from "./navigation.js";
const $ = id => document.getElementById(id),
  input = $("entry"),
  status = $("status");
let puzzle, values = {},
  store, active = null,
  index = 0,
  cellEls = new Map(),
  clueEls = new Map(),
  generation = 0,
  loading = true;
const sessionId = JSON.parse($("session-id").textContent);
let shared = null;
const message = text => {
  status.textContent = text;
};

if (sessionId) shared = sharedSession(sessionId, message);

const fullClue = document.createElement("div");
fullClue.className = "full-clue";
fullClue.popover = "auto";
document.querySelector(".active-clue-bar").append(fullClue);

// Rebuild the clue only when the selection changes, so typing and polling keep its focus.
function showClue(slot) {
  const clue = puzzle.clues.find(c => key(c) === key(slot));
  const across = slot.direction === "across";
  const direction = document.createElement("strong");
  direction.className = "clue-direction";
  direction.setAttribute("role", "img");
  direction.setAttribute("aria-label", `${slot.number} ${across ? "מאוזן" : "מאונך"}`);
  direction.textContent = `${slot.number} ${across ? "←" : "↓"}`;

  const text = document.createElement("button");
  text.type = "button";
  text.className = "clue-text";
  text.append(clue.text + " ", enumeration(clue, slot.length));
  fullClue.hidePopover();
  fullClue.replaceChildren(clue.text + " ", enumeration(clue, slot.length));
  text.popoverTargetElement = fullClue;
  text.title = text.textContent;
  $("active-clue").replaceChildren(direction, text);
}

function paint() {
  for (const [coord, el] of cellEls) {
    el.querySelector(".letter").textContent = values[coord] || "";
    el.classList.toggle("selected", !!active?.cells.some(c => c.join(",") === coord));
    el.classList.toggle("active", !!active && active.cells[index].join(",") === coord);
    el.tabIndex = active && active.cells[index].join(",") === coord ? 0 : -1;
    el.setAttribute("aria-label", `שורה ${+coord.split(",")[0]+1}, עמודה ${+coord.split(",")[1]+1}, ${values[coord] || "ריק"}`);
  }
  for (const slot of puzzle?.template.slots || []) {
    const el = clueEls.get(key(slot));
    if (!el) continue;
    const done = Boolean(completedAnswer(slot, values));
    el.classList.toggle("selected", slot === active);
    el.classList.toggle("completed", done);
    el.querySelector(".completion-mark").hidden = !done;
  }
  $("completion-mark").hidden = !active || !completedAnswer(active, values);
  if (active) {
    input.setAttribute("aria-label", `הזנת אות · ${active.number} ${active.direction==="across"?"מאוזן":"מאונך"} · אות ${index+1} מתוך ${active.length}`);
    const cell = cellEls.get(active.cells[index].join(","));
    input.style.top = `${cell.offsetTop}px`;
    input.style.left = `${cell.offsetLeft}px`;
  }
  shared?.paint(active, clueEls);
}

function select(slot, at = 0, focus = true) {
  if (active !== slot) showClue(slot);
  active = slot;
  index = at;
  paint();
  if (focus) input.focus({
    preventScroll: true
  });
}

function persist() {
  shared?.edited();
  store.save(values, shared?.snapshot());
  paint();
}

function enter(text) {
  if (loading || !active) return;
  index = writeWord(values, active.cells, index, letters(text));
  persist();
}

function draw() {
  cellEls.clear();
  clueEls.clear();
  $("grid").replaceChildren();
  for (let row = 0; row < 11; row++)
    for (let col = 0; col < 11; col++) {
      const black = puzzle.template.rows[row][col] === "#",
        el = document.createElement(black ? "div" : "button");
      el.className = black ? "cell black" : "cell";
      if (!black) {
        const number = Object.entries(puzzle.template.numbers).find(([, c]) => c[0] === row && c[1] === col)?.[0];
        const label = document.createElement("span");
        label.className = "letter";
        el.append(label);
        if (number) {
          const n = document.createElement("span");
          n.className = "number";
          n.textContent = number;
          el.append(n);
        }
        const slots = puzzle.template.slots.filter(s => s.cells.some(c => c[0] === row && c[1] === col));
        el.addEventListener("click", () => {
          const same = active?.cells[index].join(",") === `${row},${col}`;
          const slot = (same ? slots.find(s => key(s) !== key(active)) : slots.find(s => active && key(s) === key(active))) || slots[0];
          select(slot, slot.cells.findIndex(c => c[0] === row && c[1] === col));
        });
        cellEls.set(`${row},${col}`, el);
      } else el.setAttribute("aria-hidden", "true");
      $("grid").append(el);
    }
  for (const d of ["across", "down"]) {
    $(d).replaceChildren();
    for (const slot of puzzle.template.slots.filter(s => s.direction === d)) {
      const clue = puzzle.clues.find(c => key(c) === key(slot)),
        li = document.createElement("li"),
        button = document.createElement("button");
      button.className = "clue";
      button.append(`${slot.number}. ${clue.text} `, enumeration(clue, slot.length));
      button.addEventListener("click", () => select(slot));
      const mark = $("completion-mark").cloneNode(true);
      mark.removeAttribute("id");
      button.append(mark);
      if (shared) {
        const badge = $("active-count").cloneNode(true);
        badge.removeAttribute("id");
        button.append(badge);
      }
      li.append(button);
      $(d).append(li);
      clueEls.set(key(slot), button);
    }
  }
  select(puzzle.template.slots[0], 0, false);
}
async function load(id = "latest") {
  const current = ++generation;
  loading = true;
  document.querySelector(".workspace").inert = true;
  document.querySelector(".workspace").setAttribute("aria-busy", "true");
  input.disabled = true;
  input.blur();
  input.value = "";
  message("טוען תשבץ…");
  try {
    const data = await api(`${id}/`);
    if (current !== generation) return;
    if (data.puzzle === null) {
      puzzle = null;
      active = null;
      values = {};
      cellEls.clear();
      clueEls.clear();
      for (const id of ["grid", "across", "down"]) $(id).replaceChildren();
      $("title").textContent = "עדיין אין תשבצים";
      message("בעל האתר יוסיף כאן את התשבץ הראשון.");
      return;
    }
    puzzle = data;
    $("title").textContent = puzzle.title;
    $("puzzles").value = puzzle.id;
    const cells = new Set(puzzle.template.slots.flatMap(s => s.cells.map(c => c.join(","))));
    message("");
    store = progress(JSON.parse($("user-id").textContent), sessionId ? `session:${sessionId}` : puzzle.id, cells, message);
    const hasDraft = store.has();
    values = store.load();
    active = null;
    if (shared) {
      shared.attach(puzzle.template.slots, values, store.syncState, hasDraft, () => {
        store.save(values, shared.snapshot());
      }, paint);
    }
    draw();
  } catch (e) {
    if (current !== generation) return;
    if (puzzle) {
      $("puzzles").value = puzzle.id;
      paint();
    } else {
      $("title").textContent = "לא ניתן לטעון תשבץ";
    }
    message(e.message);
  } finally {
    if (current === generation) {
      loading = false;
      input.disabled = !puzzle;
      document.querySelector(".workspace").inert = !puzzle;
      document.querySelector(".workspace").setAttribute("aria-busy", "false");
    }
  }
}
// Keep the pinned clue aligned with the visible viewport when a native keyboard opens.
function viewport() {
  document.documentElement.style.setProperty("--viewport-top", `${window.visualViewport?.offsetTop || 0}px`);
}
input.addEventListener("focus", viewport);
new ResizeObserver(([entry]) => {
  document.documentElement.style.setProperty("--active-clue-height", `${entry.target.getBoundingClientRect().height}px`);
}).observe(document.querySelector(".active-clue-bar"));
viewport();
window.visualViewport?.addEventListener("resize", viewport);
window.visualViewport?.addEventListener("scroll", viewport);
input.addEventListener("input", e => {
  if (e.isComposing) return;
  enter(input.value);
  input.value = "";
});
input.addEventListener("compositionend", () => {
  enter(input.value);
  input.value = "";
});
input.addEventListener("paste", e => {
  e.preventDefault();
  enter(e.clipboardData.getData("text"));
});
input.addEventListener("beforeinput", e => {
  if (e.inputType === "deleteContentBackward" && active && !loading) {
    e.preventDefault();
    index = erase(values, active.cells, index);
    persist();
  }
});
input.addEventListener("keydown", e => {
  if (loading || !active || e.isComposing) return;
  if (e.key === "Backspace") {
    e.preventDefault();
    index = erase(values, active.cells, index);
    persist();
    return;
  }
  if (e.key === "Delete") {
    e.preventDefault();
    delete values[active.cells[index].join(",")];
    persist();
    return;
  }
  const delta = active.direction === "across" ? {
    ArrowLeft: 1,
    ArrowRight: -1
  } : {
    ArrowDown: 1,
    ArrowUp: -1
  };
  if (e.key in delta) {
    e.preventDefault();
    index = Math.max(0, Math.min(index + delta[e.key], active.length - 1));
    paint();
  } else if (e.key === "Home" || e.key === "End") {
    e.preventDefault();
    index = e.key === "Home" ? 0 : active.length - 1;
    paint();
  } else if (e.key === " " || e.key === "Enter") {
    e.preventDefault();
    const coord = active.cells[index].join(",");
    const other = puzzle.template.slots.find(s => key(s) !== key(active) && s.cells.some(c => c.join(",") === coord));
    if (other) select(other, other.cells.findIndex(c => c.join(",") === coord));
  }
});
$("puzzles").addEventListener("change", async e => {
  const target = e.target.value;
  $("site-menu").close();
  if (shared) {
    e.target.value = puzzle.id;
    location.assign(`/?puzzle=${encodeURIComponent(target)}`);
    return;
  }
  load(e.target.value);
});
try {
  const data = await api();
  for (const p of data.puzzles) {
    const o = new Option(`${p.title} · נוסף ${date(p.created_at)}`, p.id);
    $("puzzles").add(o);
  }
  if (shared) {
    const session = await shared.load();
    await load(session.puzzle_id);
  } else {
    await load(new URLSearchParams(location.search).get("puzzle") || "latest");
  }
} catch (e) {
  message(e.message);
}

$("solve-together").addEventListener("click", async () => {
  if (!puzzle || loading) return;
  $("solve-together").disabled = true;
  try {
    const session = await sessionApi("", {method: "POST", body: JSON.stringify({puzzle_id: puzzle.id})});
    location.assign(`/sessions/${session.id}/`);
  } catch (e) { $("site-menu").close(); message(e.message); $("solve-together").disabled = false; }
});
$("copy-invite").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("invite-link").value); $("site-menu").close(); message("הקישור הועתק."); }
  catch { $("invite-link").select(); message("אפשר להעתיק את הקישור מהשדה המסומן."); }
});
$("revoke-invite").addEventListener("click", () => {
  if (window.confirm("לבטל את קישור ההצטרפות? משתתפים קיימים יישארו במפגש.")) { $("site-menu").close(); void shared?.revoke(); }
});
