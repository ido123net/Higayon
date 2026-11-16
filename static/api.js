export async function api(path = "", options = {}) {
  const csrf = document.cookie.split("; ").find(v => v.startsWith("csrftoken="))?.split("=")[1];
  let response;
  try {
    response = await fetch(`/api/v1/puzzles/${path}`, {
      credentials: "same-origin",
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf || "",
        ...options.headers
      }
    });
  } catch {
    throw new Error("אין חיבור לשרת. הנתונים שהזנת נשארו בדף; אפשר לנסות שוב.");
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("השרת לא זמין כרגע. אפשר לנסות שוב.");
  }
  if (!response.ok) throw new Error(data.error || "הבקשה נכשלה. אפשר לנסות שוב.");
  return data;
}
export const date = value => new Date(value).toLocaleDateString("he-IL");
export const key = slot => `${slot.direction}:${slot.number}`;
export function enumeration(clue, length) {
  const span = document.createElement("bdi");
  span.className = "enumeration";
  span.dir = "ltr";
  span.textContent = `(${(clue.enumeration || [length]).join(", ")})`;
  return span;
}
