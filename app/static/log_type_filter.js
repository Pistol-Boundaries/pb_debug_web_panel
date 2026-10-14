(() => {
  document.querySelectorAll('[data-multiselect]').forEach(picker => {
    const checkboxes = [...picker.querySelectorAll('input[type="checkbox"]')];
    const updateSummary = () => {
      const count = checkboxes.filter(input => input.checked).length;
      picker.querySelector('summary').textContent = count ? `${count} selected` : picker.dataset.emptyLabel;
    };
    checkboxes.forEach(input => input.addEventListener('change', updateSummary));
    picker.querySelector('[data-clear-selection]').addEventListener('click', () => {
      checkboxes.forEach(input => { input.checked = false; });
      updateSummary();
    });
  });
})();
