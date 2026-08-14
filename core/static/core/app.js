(function () {
    "use strict";

    // --- Переключение полей дат для произвольного периода ---
    var periodSelect = document.querySelector(".period-select");
    if (periodSelect) {
        var dateGroup = document.querySelector(".period-date-group");
        function toggleDateFields() {
            var show = periodSelect.value === "custom";
            if (dateGroup) {
                dateGroup.style.display = show ? "block" : "none";
            }
        }
        toggleDateFields();
        periodSelect.addEventListener("change", toggleDateFields);
    }

    // --- Модальное окно подтверждения удаления ---
    var modal = document.getElementById("confirm-modal");
    var modalText = document.getElementById("confirm-modal-text");
    var okBtn = document.getElementById("confirm-ok");
    var cancelBtn = document.getElementById("confirm-cancel");
    var pendingForm = null;

    function showModal(text, form) {
        modalText.textContent = text;
        pendingForm = form;
        modal.removeAttribute("hidden");
    }
    function hideModal() {
        modal.setAttribute("hidden", "");
        pendingForm = null;
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest(".delete-btn");
        if (!trigger) {
            return;
        }
        event.preventDefault();
        var name = trigger.getAttribute("data-player-name") || "";
        var form = trigger.closest("form");
        var message = "Вы уверены, что хотите удалить игрока " + name +
            "? При удалении вся история о нём будет также удалена!";
        showModal(message, form);
    });

    if (okBtn) {
        okBtn.addEventListener("click", function () {
            if (pendingForm) {
                pendingForm.submit();
            }
        });
    }
    if (cancelBtn) {
        cancelBtn.addEventListener("click", hideModal);
    }
    if (modal) {
        modal.addEventListener("click", function (event) {
            if (event.target === modal) {
                hideModal();
            }
        });
    }
})();
