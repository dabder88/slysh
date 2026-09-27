import { t } from "./i18n.js";
/** Оборачивает input[type=password] кнопкой показа/скрытия значения. */
export function initSecretFields(root = document) {
  const scope = root && root.querySelectorAll ? root : document;
  for (const input of scope.querySelectorAll('input[type="password"]')) {
    if (input.closest(".secret-field-wrap")) {
      continue;
    }
    const parent = input.parentNode;
    if (!parent) {
      continue;
    }
    const wrap = document.createElement("div");
    wrap.className = "secret-field-wrap";
    parent.insertBefore(wrap, input);
    wrap.appendChild(input);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secret-field-toggle";
    btn.setAttribute("aria-label", t("secretField.show"));
    btn.setAttribute("aria-pressed", "false");
    const icon = document.createElement("span");
    icon.className = "material-symbols-outlined";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "visibility";
    btn.appendChild(icon);

    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      icon.textContent = show ? "visibility_off" : "visibility";
      btn.setAttribute("aria-label", show ? t("secretField.hide") : t("secretField.show"));
      btn.setAttribute("aria-pressed", show ? "true" : "false");
    });

    wrap.appendChild(btn);
  }
}
