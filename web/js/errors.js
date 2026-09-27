import { showToast } from "./api.js";
import { t } from "./i18n.js";

export function reportError(context, err) {
  const msg = err?.message || String(err);
  console.error(context, err);
  showToast(`${context}: ${msg}`);
  const banner = document.getElementById("boot-error");
  if (banner) {
    banner.hidden = false;
    banner.textContent = `${context}: ${msg}`;
  }
}
