export function msIcon(name, { filled = false, size = "" } = {}) {
  const el = document.createElement("span");
  const sizeClass = size === "lg" ? " ms-lg" : size === "md" ? " ms-md" : "";
  el.className = `material-symbols-outlined${filled ? " is-filled" : ""}${sizeClass}`;
  el.setAttribute("aria-hidden", "true");
  el.textContent = name;
  return el;
}
