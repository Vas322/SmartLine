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

    // --- Модальное окно подтверждения удаления / уведомления ---
    var modal = document.getElementById("confirm-modal");
    var modalText = document.getElementById("confirm-modal-text");
    var okBtn = document.getElementById("confirm-ok");
    var cancelBtn = document.getElementById("confirm-cancel");
    var pendingForm = null;

    function showModal(text, form, hideCancel) {
        modalText.textContent = text;
        pendingForm = form || null;
        if (cancelBtn) {
            cancelBtn.hidden = !!hideCancel;
        }
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
        showModal(message, form, false);
    });

    if (okBtn) {
        okBtn.addEventListener("click", function () {
            if (pendingForm) {
                pendingForm.submit();
            } else {
                hideModal();
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

    // --- Модальное уведомление об успешном редактировании ---
    var notify = document.getElementById("edit-notify");
    if (notify && notify.dataset.message) {
        showModal(notify.dataset.message, null, true);
    }

    // --- Авто-рост текстовых полей под содержимое ---
    function autoGrow(el) {
        el.style.height = "auto";
        el.style.height = el.scrollHeight + "px";
    }
    var growables = document.querySelectorAll("textarea.auto-grow");
    Array.prototype.forEach.call(growables, function (el) {
        autoGrow(el);
        el.addEventListener("input", function () { autoGrow(el); });
    });
})();