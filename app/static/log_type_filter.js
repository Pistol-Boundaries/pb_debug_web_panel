(() => {
  if (!document.getElementById("log-type-summary")) return;
      const typeCheckboxes = [...document.querySelectorAll('input[name="log_type"]')];
      function updateTypeSummary() {
        const count = typeCheckboxes.filter(input => input.checked).length;
        document.getElementById("log-type-summary").textContent = count ? `${count} selected` : "All log types";
      }
      typeCheckboxes.forEach(input => input.addEventListener("change", updateTypeSummary));
      document.getElementById("clear-log-types").addEventListener("click", () => {
        typeCheckboxes.forEach(input => { input.checked = false; });
        updateTypeSummary();
      });
})();
