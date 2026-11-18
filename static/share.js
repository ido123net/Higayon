const link = document.getElementById("share-url");
const status = document.getElementById("share-status");
document.getElementById("copy-share").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(link.value);
    status.textContent = "הקישור הועתק.";
  } catch {
    link.focus();
    link.select();
    status.textContent = "אפשר להעתיק את הקישור המסומן.";
  }
});
