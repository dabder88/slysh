/** Wait for bootstrap token (injected HTML or pywebview bridge) and POST /api/ui/session. */

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function tryBridgeBootstrap() {
  const bridge = window.pywebview?.api;
  if (!bridge?.ui_bootstrap_token) {
    return "";
  }
  try {
    const token = await bridge.ui_bootstrap_token();
    if (typeof token === "string" && token.trim()) {
      return token.trim();
    }
  } catch (_) {
    /* retry */
  }
  return "";
}

async function readBootstrapToken() {
  const deadline = Date.now() + 12_000;
  while (Date.now() < deadline) {
    const fromBridge = await tryBridgeBootstrap();
    if (fromBridge) {
      return fromBridge;
    }
    const fromDom = window.__SLYSH_BOOTSTRAP__;
    if (typeof fromDom === "string" && fromDom.trim()) {
      return fromDom.trim();
    }
    await sleep(50);
  }
  return "";
}

export async function establishUiSession() {
  const token = await readBootstrapToken();
  if (!token) {
    return;
  }
  const res = await fetch("/api/ui/session", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Slysh-Bootstrap": token,
    },
    body: "{}",
  });
  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") {
        message = parsed.detail;
      }
    } catch (_) {
      /* keep raw */
    }
    throw new Error(message || `UI session HTTP ${res.status}`);
  }
}
