export const DIALOG_ACTION_ATTR = "data-dialog-action";

export function initDialogs({ onConfigOpen, onConfigClose } = {}) {
  const dialog = document.querySelector("#confirm-dialog");
  const drawer = document.querySelector("#config-drawer");
  const close = document.querySelector("#drawer-close");
  const dismiss = document.querySelector("#drawer-dismiss");
  const toastRegion = document.querySelector("#toast-region");
  let lastFocus = null;

  function confirmAction({ title, message, acceptLabel = "Confirmar", tone = "accent" }) {
    if (!dialog) return Promise.resolve(false);
    dialog.querySelector("#confirm-title").textContent = title;
    dialog.querySelector("#confirm-message").textContent = message;
    const accept = dialog.querySelector("#confirm-accept");
    const cancel = dialog.querySelector("#confirm-cancel");
    accept.textContent = acceptLabel;
    accept.className =
      tone === "danger" ? "af-button af-button--danger" : "af-button af-button--accent";
    return new Promise((resolve) => {
      function cleanup(result) {
        dialog.removeEventListener("close", handleClose);
        accept.removeEventListener("click", handleAccept);
        cancel.removeEventListener("click", handleCancel);
        if (dialog.open) dialog.close();
        resolve(result);
      }
      function handleClose() {
        cleanup(confirmed);
      }
      function handleAccept() {
        confirmed = true;
        cleanup(true);
      }
      function handleCancel() {
        cleanup(false);
      }
      let confirmed = false;
      dialog.addEventListener("close", handleClose);
      accept.addEventListener("click", handleAccept);
      cancel.addEventListener("click", handleCancel);
      dialog.showModal();
      accept.focus();
    });
  }

  function openDrawer() {
    if (!drawer) return;
    lastFocus = document.activeElement;
    drawer.showModal();
    document.body.classList.add("af-drawer-open");
    onConfigOpen?.();
    drawer.querySelector("#drawer-close")?.focus();
  }

  function closeDrawer({ force = false } = {}) {
    if (!drawer) return;
    if (!drawer.open) return;
    if (!force && drawer.dataset.dirty === "true") {
      void confirmAction({
        title: "Descartar cambios",
        message: "Hay cambios sin guardar en el formulario. ¿Quieres descartarlos?",
        acceptLabel: "Descartar",
        tone: "danger",
      }).then((accepted) => {
        if (accepted) closeDrawer({ force: true });
      });
      return;
    }
    drawer.close();
  }

  drawer?.addEventListener("click", (event) => {
    if (event.target === drawer) closeDrawer();
  });
  drawer?.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDrawer();
  });
  drawer?.addEventListener("close", () => {
    document.body.classList.remove("af-drawer-open");
    onConfigClose?.();
    lastFocus?.focus?.();
  });
  close?.addEventListener("click", () => closeDrawer());
  dismiss?.addEventListener("click", () => closeDrawer());

  function toast(message, tone = "success") {
    if (!toastRegion) return;
    const item = document.createElement("div");
    item.className = `af-toast af-toast--${tone}`;
    item.setAttribute("role", tone === "error" ? "alert" : "status");
    item.textContent = message;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "af-toast__close";
    button.setAttribute("aria-label", "Cerrar aviso");
    button.textContent = "×";
    button.addEventListener("click", () => item.remove());
    item.append(button);
    toastRegion.append(item);
    window.setTimeout(() => item.remove(), 6000);
  }

  return {
    confirmAction,
    openDrawer,
    closeDrawer,
    toast,
    isDrawerOpen: () => Boolean(drawer?.open),
  };
}
