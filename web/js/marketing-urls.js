const ABOUT_RU = "https://slyshai.pro/?utm_source=soft&utm_medium=ru";
const ABOUT_EN = "https://slyshai.pro/en/?utm_source=soft&utm_medium=en";

export function marketingUrlsForLocale(locale) {
  const isEn = locale === "en";
  const about = isEn ? ABOUT_EN : ABOUT_RU;
  return { about, support: `${about}#support` };
}

/** True when URL is one of the built-in slyshai.pro marketing links (any locale). */
export function isDefaultSlyshaiMarketingUrl(url, kind = "about") {
  const trimmed = String(url || "").trim();
  if (!trimmed) {
    return false;
  }
  if (kind === "support") {
    return trimmed === `${ABOUT_RU}#support` || trimmed === `${ABOUT_EN}#support`;
  }
  const base = trimmed.split("#")[0];
  return base === ABOUT_RU || base === ABOUT_EN;
}

/** Align default marketing URLs with active UI locale; leave custom URLs untouched. */
export function resolveMarketingUrlsFromApi(info, locale) {
  const defaults = marketingUrlsForLocale(locale === "en" ? "en" : "ru");
  let about = String(info?.about_url || "").trim();
  let support = String(info?.support_url || "").trim();
  if (!about || isDefaultSlyshaiMarketingUrl(about, "about")) {
    about = defaults.about;
  }
  if (!support || isDefaultSlyshaiMarketingUrl(support, "support")) {
    support = defaults.support;
  }
  return { about, support };
}
