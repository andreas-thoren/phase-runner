// Account delete confirmation dialog.
// Opens a modal when the delete button is clicked.
// Confirm button is disabled until the user types "DELETE".

const deleteBtn = document.getElementById("delete-btn");
const dialog = document.getElementById("confirm-delete-dialog");
const confirmInput = document.getElementById("confirm-delete-input");
const confirmBtn = document.getElementById("dialog-confirm");
const cancelBtn = document.getElementById("dialog-cancel");
const closeBtn = document.getElementById("dialog-close");
const mainForm = document.getElementById("main-form");

if (deleteBtn && dialog && confirmInput && confirmBtn && mainForm) {
  deleteBtn.addEventListener("click", () => {
    confirmInput.value = "";
    confirmBtn.disabled = true;
    dialog.showModal();
    confirmInput.focus();
  });

  confirmInput.addEventListener("input", () => {
    confirmBtn.disabled = confirmInput.value.trim() !== "DELETE";
  });

  confirmBtn.addEventListener("click", () => {
    dialog.close();
    mainForm.submit();
  });

  if (cancelBtn) cancelBtn.addEventListener("click", () => dialog.close());
  if (closeBtn) closeBtn.addEventListener("click", () => dialog.close());
}
