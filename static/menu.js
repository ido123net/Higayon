const menu = document.getElementById("site-menu");
const trigger = document.getElementById("open-menu");

trigger.addEventListener("click", () => menu.showModal());
document.getElementById("close-menu").addEventListener("click", () => menu.close());
menu.addEventListener("click", event => {
  if (event.target !== menu) return;
  const bounds = menu.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom) menu.close();
});
menu.addEventListener("close", () => {
  if (!document.querySelector("dialog[open]")) trigger.focus({preventScroll: true});
});
