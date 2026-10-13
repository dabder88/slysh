/** Shared pointer/keyboard column resizer (editor player panel, sidebar, …). */

export function bindPanelResizer(handle, onDrag) {
  if (!handle || handle.dataset.bound) {
    return;
  }
  handle.dataset.bound = "1";

  const startDrag = (clientX) => {
    let lastX = clientX;
    handle.classList.add("is-active");
    document.body.classList.add("is-resizing");

    const onMove = (event) => {
      const x = event.clientX ?? lastX;
      const delta = x - lastX;
      lastX = x;
      onDrag(delta);
    };

    const onUp = () => {
      handle.classList.remove("is-active");
      document.body.classList.remove("is-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    handle.setPointerCapture?.(event.pointerId);
    startDrag(event.clientX);
  });

  handle.addEventListener("keydown", (event) => {
    const step = event.shiftKey ? 24 : 8;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowRight" ? step : -step;
      onDrag(delta);
    }
  });
}
