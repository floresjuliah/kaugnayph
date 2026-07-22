document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("positionConfirmModal");

    if (!modal) {
        return;
    }

    const title = document.getElementById("positionConfirmTitle");
    const message = document.getElementById("positionConfirmMessage");
    const icon = document.getElementById("positionConfirmIcon");
    const confirmButton = document.getElementById("positionConfirmButton");
    const cancelButton = document.getElementById("positionCancelButton");

    let activeForm = null;

    function closeModal() {
        modal.classList.remove("active", "danger", "success");
        activeForm = null;
    }

    document
        .querySelectorAll("form[data-position-confirm]")
        .forEach(function (form) {
            form.addEventListener("submit", function (event) {
                event.preventDefault();

                if (!form.checkValidity()) {
                    form.reportValidity();
                    return;
                }

                activeForm = form;

                title.textContent =
                    form.dataset.confirmTitle || "Confirm Action";

                message.textContent =
                    form.dataset.confirmMessage ||
                    "Are you sure you want to continue?";

                confirmButton.textContent =
                    form.dataset.confirmButton || "Continue";

                const variant =
                    form.dataset.confirmVariant || "primary";

                modal.classList.toggle(
                    "danger",
                    variant === "danger"
                );

                modal.classList.toggle(
                    "success",
                    variant === "success"
                );

                const configuredIcon =
                    form.dataset.confirmIcon ||
                    (
                        variant === "danger"
                            ? "fa-solid fa-triangle-exclamation"
                            : variant === "success"
                                ? "fa-solid fa-rotate-right"
                                : "fa-solid fa-circle-question"
                    );

                if (variant === "danger") {
                    confirmButton.className = "btn btn-danger";
                } else {
                    confirmButton.className =
                        "admin-primary-btn border-0";
                }

                icon.className = configuredIcon;

                modal.classList.add("active");
            });
        });

    confirmButton.addEventListener("click", function () {
        if (!activeForm) {
            return;
        }

        const formToSubmit = activeForm;

        confirmButton.disabled = true;
        closeModal();

        formToSubmit.submit();
    });

    cancelButton.addEventListener("click", closeModal);

    modal.addEventListener("click", function (event) {
        if (event.target === modal) {
            closeModal();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (
            event.key === "Escape" &&
            modal.classList.contains("active")
        ) {
            closeModal();
        }
    });
});
