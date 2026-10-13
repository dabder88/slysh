let bound = false;

function hideAppExitModal() {
  const modal = document.getElementById("app-exit-modal");
  if (modal) {
    modal.hidden = true;
  }
  const remember = document.getElementById("app-exit-remember");
  if (remember) {
    remember.checked = false;
  }
}

function showAppExitModal() {
  const modal = document.getElementById("app-exit-modal");
  if (!modal) {
    return false;
  }
  if (!modal.hidden) {
    return true;
  }
  modal.hidden = false;
  document.getElementById("app-exit-cancel")?.focus();
  return true;
}

async function confirmAppExit() {
  const rememberEl = document.getElementById("app-exit-remember");
  const remember = Boolean(rememberEl?.checked);
  const api = window.pywebview?.api;
  if (api?.finish_app_exit) {
    window.__appExitInProgress = true;
    hideAppExitModal();
    await api.finish_app_exit(remember, true);
    return;
  }
  hideAppExitModal();
  window.close();
}

function bindAppExitModal() {
  if (bound) {
    return;
  }
  bound = true;
  const modal = document.getElementById("app-exit-modal");
  if (!modal) {
    return;
  }
  document.getElementById("app-exit-confirm")?.addEventListener("click", () => {
    confirmAppExit().catch(() => hideAppExitModal());
  });
  document.getElementById("app-exit-cancel")?.addEventListener("click", hideAppExitModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) {
      hideAppExitModal();
    }
  });
}

export function initAppExit() {
  bindAppExitModal();
  window.__promptAppExit = () => {
    if (window.__appExitInProgress) {
      return false;
    }
    showAppExitModal();
    const modal = document.getElementById("app-exit-modal");
    return Boolean(modal && !modal.hidden);
  };
}
