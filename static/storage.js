export const normalize = text => text.replace(/[ךםןףץ]/g, c => ({
  ך: "כ",
  ם: "מ",
  ן: "נ",
  ף: "פ",
  ץ: "צ"
})[c]);
export const letters = text => [...normalize(text)].filter(c => /^[א-ת]$/.test(c));
export function progress(user, puzzle, cells, warning, storage = () => window.localStorage) {
  const id = `higayon:v1:${user}:${puzzle}`;
  return {
    has() {
      try { return storage().getItem(id) !== null; } catch { return false; }
    },
    load() {
      try {
        const raw = JSON.parse(storage().getItem(id) || "{}");
        return Object.fromEntries(Object.entries(raw || {}).filter(([k, v]) => cells.has(k) && typeof v === "string" && /^[א-ת]$/.test(v)).map(([k, v]) => [k, normalize(v)]));
      } catch {
        warning("לא ניתן לקרוא שמירה בדפדפן. ההתקדמות זמינה כרגע בדף בלבד.");
        return {};
      }
    },
    save(value) {
      try {
        storage().setItem(id, JSON.stringify(value));
      } catch {
        warning("לא ניתן לשמור בדפדפן. ההתקדמות זמינה כרגע בדף בלבד.");
      }
    }
  };
}
