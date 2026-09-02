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

    // --- Переключение форм добавления тарифов на странице настроек ---
    document.querySelectorAll('[data-toggle-form]').forEach(el => el.addEventListener('click', () => { const target = document.getElementById(el.getAttribute('data-toggle-form')); if (!target) return; if (target.hasAttribute('hidden')) target.removeAttribute('hidden'); else target.setAttribute('hidden', ''); }));

    // --- Авто-рост текстовых полей под содержимое ---
    // Ниже минимума (min-height, см. CSS — ~4 строки) поле не сжимается.
    function autoGrow(el) {
        var minHeight = parseInt(window.getComputedStyle(el).minHeight, 10) || 0;
        el.style.height = "auto";
        el.style.height = Math.max(el.scrollHeight, minHeight) + "px";
    }
    var growables = document.querySelectorAll("textarea.auto-grow");
    Array.prototype.forEach.call(growables, function (el) {
        autoGrow(el);
        el.addEventListener("input", function () { autoGrow(el); });
    });

    // ============================================================
    // Исходящие сообщения: табы, модальные окна, отправка (AJAX)
    // ============================================================
    var MAX_TEXT_LENGTH = 4096;

    function getCookie(name) {
        var match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
        return match ? decodeURIComponent(match[2]) : null;
    }

    // --- Переключение табов без перезагрузки страницы ---
    var tabButtons = document.querySelectorAll(".tab-btn");
    var tabPanels = document.querySelectorAll(".tab-panel");

    function switchTab(tab) {
        tabButtons.forEach(function (btn) {
            var active = btn.getAttribute("data-tab") === tab;
            btn.classList.toggle("active", active);
        });
        tabPanels.forEach(function (panel) {
            panel.classList.toggle("hidden", panel.getAttribute("data-panel") !== tab);
        });
        var url = new URL(window.location.href);
        if (url.searchParams.get("tab") !== tab) {
            url.searchParams.set("tab", tab);
            history.replaceState(null, "", url.toString());
        }
    }
    tabButtons.forEach(function (btn) {
        btn.addEventListener("click", function () {
            switchTab(btn.getAttribute("data-tab"));
        });
    });

    // --- Вспомогательные: открытие/закрытие модалок ---
    function openModal(id) {
        var el = document.getElementById(id);
        if (el) { el.removeAttribute("hidden"); }
    }
    function closeModal(id) {
        var el = document.getElementById(id);
        if (el) { el.setAttribute("hidden", ""); }
    }

    // Общая валидация текста: возвращает нормализованный текст или null (пусто).
    // При превышении 4096 символов — обрезает и показывает предупреждение.
    function validateText(textarea, hintEl, errorEl) {
        var raw = textarea.value || "";
        var hint = raw.length + "/" + MAX_TEXT_LENGTH;
        var errorMsg = "";
        if (raw.trim() === "") {
            errorMsg = "Текст не может быть пустым.";
        } else if (raw.length > MAX_TEXT_LENGTH) {
            textarea.value = raw.slice(0, MAX_TEXT_LENGTH);
            raw = textarea.value;
            hint = raw.length + "/" + MAX_TEXT_LENGTH + " (обрезано)";
            errorMsg = "Текст превышал 4096 символов и был обрезан.";
        }
        if (hintEl) { hintEl.textContent = hint; }
        if (errorEl) {
            if (errorMsg) {
                errorEl.textContent = errorMsg;
                errorEl.removeAttribute("hidden");
            } else {
                errorEl.setAttribute("hidden", "");
            }
        }
        return raw.trim() !== "" ? raw : null;
    }

    // --- Модальное окно «Ответить» ---
    var replyModal = document.getElementById("reply-modal");
    var replyOriginal = document.getElementById("reply-original-text");
    var replyTextarea = document.getElementById("reply-text");
    var replyHint = document.getElementById("reply-char-hint");
    var replyError = document.getElementById("reply-modal-error");
    var replyNext = document.getElementById("reply-next");
    var replyCancel = document.getElementById("reply-cancel");
    var currentReplyMessageId = null;

    function updateReplyNext() {
        var valid = validateText(replyTextarea, replyHint, null);
        replyNext.disabled = !valid;
        // Живая проверка кнопки не должна показывать ошибку — только счётчик символов.
        replyError.setAttribute("hidden", "");
    }

    document.addEventListener("click", function (event) {
        var trigger = event.target.closest(".reply-btn");
        if (!trigger) { return; }
        var row = trigger.closest(".incoming-row");
        if (!row) { return; }
        currentReplyMessageId = row.getAttribute("data-message-id");
        replyOriginal.textContent = row.getAttribute("data-message-text") || "";
        replyTextarea.value = "";
        replyError.setAttribute("hidden", "");
        updateReplyNext();
        openModal("reply-modal");
        replyTextarea.focus();
    });

    if (replyTextarea) {
        replyTextarea.addEventListener("input", function () {
            updateReplyNext();
            autoGrow(replyTextarea);
        });
    }
    var replySending = false;
    if (replyNext) {
        replyNext.addEventListener("click", function () {
            var text = validateText(replyTextarea, replyHint, replyError);
            if (!text || replySending) { return; }
            replySending = true;
            replyNext.disabled = true;
            ajaxSend(
                "/telegram-messages/send-reply/",
                { telegram_message_id: currentReplyMessageId, text: text },
                replyError,
                function () { closeModal("reply-modal"); },
                function () {
                    replySending = false;
                    updateReplyNext();
                }
            );
        });
    }
    if (replyCancel) {
        replyCancel.addEventListener("click", function () { closeModal("reply-modal"); });
    }

    // --- Модальное окно «Новое сообщение» ---
    var newMsgBtn = document.getElementById("new-message-btn");
    var newMsgTextarea = document.getElementById("new-message-text");
    var newMsgTopic = document.getElementById("new-message-topic");
    var newMsgHint = document.getElementById("new-message-char-hint");
    var newMsgError = document.getElementById("new-message-modal-error");
    var newMsgNext = document.getElementById("new-message-next");
    var newMsgCancel = document.getElementById("new-message-cancel");

    function updateNewMsgNext() {
        var valid = validateText(newMsgTextarea, newMsgHint, null);
        newMsgNext.disabled = !valid;
        newMsgError.setAttribute("hidden", "");
    }

    if (newMsgBtn) {
        newMsgBtn.addEventListener("click", function () {
            newMsgTextarea.value = "";
            newMsgTopic.value = "";
            newMsgError.setAttribute("hidden", "");
            updateNewMsgNext();
            openModal("new-message-modal");
            newMsgTextarea.focus();
        });
    }
    if (newMsgTextarea) {
        newMsgTextarea.addEventListener("input", function () {
            updateNewMsgNext();
            autoGrow(newMsgTextarea);
        });
    }
    var newMsgSending = false;
    if (newMsgNext) {
        newMsgNext.addEventListener("click", function () {
            var text = validateText(newMsgTextarea, newMsgHint, newMsgError);
            if (!text || newMsgSending) { return; }
            var threadId = newMsgTopic.value || "";
            newMsgSending = true;
            newMsgNext.disabled = true;
            ajaxSend(
                "/telegram-messages/send-message/",
                { text: text, thread_id: threadId || null },
                newMsgError,
                function () { closeModal("new-message-modal"); },
                function () {
                    newMsgSending = false;
                    updateNewMsgNext();
                }
            );
        });
    }
    if (newMsgCancel) {
        newMsgCancel.addEventListener("click", function () { closeModal("new-message-modal"); });
    }

    // --- Эмодзи-палитра в модальных окнах сообщений ---
    var EMOJIS = [
        "😀", "😂", "😊", "😍", "🤔", "😎", "😢", "😡",
        "🔥", "⚔️", "🛡️", "💰", "✅", "❌", "📌", "💬",
        "🚀", "👍", "👎", "🙏", "☠️", "🏰", "💎", "🎉",
        "⭐", "❤️", "💯", "📢", "⏰", "🕐", "🎯", "🛡️",
        "🏆", "⚡", "💪", "🤝", "📅", "🆘", "⚠️", "❗"
    ];

    function insertEmoji(textarea, emoji) {
        var start = textarea.selectionStart;
        var end = textarea.selectionEnd;
        var value = textarea.value;
        textarea.value = value.slice(0, start) + emoji + value.slice(end);
        textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
        autoGrow(textarea);
        textarea.focus();
        // Обновляем счётчик символов и состояние кнопки отправки.
        if (textarea === replyTextarea) {
            updateReplyNext();
        } else if (textarea === newMsgTextarea) {
            updateNewMsgNext();
        }
    }

    function closeAllPalettes(except) {
        document.querySelectorAll(".emoji-palette").forEach(function (p) {
            if (p !== except) { p.classList.add("hidden"); }
        });
    }

    document.querySelectorAll(".emoji-palette").forEach(function (palette) {
        var targetId = palette.getAttribute("data-for");
        EMOJIS.forEach(function (emoji) {
            var span = document.createElement("span");
            span.className = "emoji-item";
            span.textContent = emoji;
            span.addEventListener("click", function (event) {
                event.stopPropagation();
                var textarea = document.getElementById(targetId);
                if (textarea) { insertEmoji(textarea, emoji); }
            });
            palette.appendChild(span);
        });
    });

    document.querySelectorAll(".emoji-toggle").forEach(function (btn) {
        btn.addEventListener("click", function (event) {
            event.stopPropagation();
            var palette = document.querySelector(
                '.emoji-palette[data-for="' + btn.getAttribute("data-for") + '"]'
            );
            var isOpen = palette && !palette.classList.contains("hidden");
            closeAllPalettes(palette);
            if (!isOpen && palette) { palette.classList.remove("hidden"); }
        });
    });

    document.addEventListener("click", function () {
        closeAllPalettes();
    });

    // --- Отправка (AJAX) ---
    var toast = document.getElementById("send-result-toast");

    function showToast(msg) {
        toast.textContent = msg;
        toast.removeAttribute("hidden");
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(function () { toast.setAttribute("hidden", ""); }, 3000);
    }

    // Отправляет payload по url. При успехе — onSuccess(); при завершении (успех/ошибка)
    // всегда вызывается onDone(). Ошибка показывается в переданном errorEl.
    function ajaxSend(url, payload, errorEl, onSuccess, onDone) {
        var xhr = new XMLHttpRequest();
        xhr.open("POST", url, true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.setRequestHeader("X-CSRFToken", getCookie("csrftoken") || "");
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== 4) { return; }
            if (onDone) { onDone(); }
            var data = {};
            try { data = JSON.parse(xhr.responseText); } catch (e) { data = {}; }
            if (xhr.status >= 200 && xhr.status < 300 && data.ok) {
                showToast("Отправлено");
                if (onSuccess) { onSuccess(); }
                // Отложенное обновление страницы, чтобы показать новое исходящее сообщение.
                setTimeout(function () { window.location.reload(); }, 600);
            } else if (errorEl) {
                errorEl.textContent = data.error || "Не удалось отправить сообщение.";
                errorEl.removeAttribute("hidden");
            }
        };
        xhr.send(JSON.stringify(payload));
    }
})();