// Data Quality page: click a status bar to filter the "by data source" table
// to that status. Click the same bar again (or "Show all") to clear it.
// Without JavaScript the table simply shows every status.
(() => {
  const chart = document.getElementById('status-chart');
  const details = document.getElementById('status-details');
  if (!chart || !details) return;

  const summary = details.querySelector('summary');
  const defaultLabel = summary.textContent;
  const note = document.getElementById('status-filter-note');
  const noteName = note.querySelector('[data-status-name]');
  const showAll = document.getElementById('status-show-all');
  const bars = [...chart.querySelectorAll('.bar-row[data-status]')];
  const rows = [...details.querySelectorAll('tbody tr[data-status]')];
  let selected = null;

  const apply = (status) => {
    selected = status;
    bars.forEach((bar) => {
      const on = bar.dataset.status === status;
      bar.classList.toggle('is-selected', on);
      bar.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    rows.forEach((row) => {
      row.hidden = status !== null && row.dataset.status !== status;
    });
    note.hidden = status === null;
    noteName.textContent = status || '';
    summary.textContent = status ? `View ${status} locations by data source` : defaultLabel;
    if (status) details.open = true;
  };

  bars.forEach((bar) => {
    const toggle = () => apply(selected === bar.dataset.status ? null : bar.dataset.status);
    bar.addEventListener('click', toggle);
    bar.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggle();
      }
    });
  });
  showAll.addEventListener('click', () => apply(null));
})();
