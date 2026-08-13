(function () {
    var select = document.querySelector(".period-select");
    if (!select) {
        return;
    }
    var dateGroup = document.querySelector(".period-date-group");

    function toggleDateFields() {
        var show = select.value === "custom";
        if (dateGroup) {
            dateGroup.style.display = show ? "block" : "none";
        }
    }

    toggleDateFields();
    select.addEventListener("change", toggleDateFields);
})();