// Data Quality page: click a bar (or tile) to filter the drill-down table
// underneath it to that item's rows. Click it again (or "Show all") to clear it.
// Without JavaScript the tables simply show every row.
//
// Used by:
//   - Locations by status            (bars/rows marked data-status)
//   - Geofences with multiple parts  (bars/rows marked data-parts)
//   - Jurisdiction path issues       (tiles/rows marked data-issue)
(() => {
  const wireBarFilter = ({
    chartId, detailsId, noteId, showAllId, attr, summaryFor,
    itemSelector = '.bar-row', labelSelector = '.bar-row-label',
  }) => {
    const chart = document.getElementById(chartId);
    const details = document.getElementById(detailsId);
    if (!chart || !details) return;

    const summary = details.querySelector('summary');
    const defaultLabel = summary.textContent;
    const note = document.getElementById(noteId);
    const noteName = note.querySelector('[data-status-name], [data-filter-name]');
    const showAll = document.getElementById(showAllId);
    const bars = [...chart.querySelectorAll(`${itemSelector}[data-${attr}]`)];
    const rows = [...details.querySelectorAll(`tbody tr[data-${attr}]`)];
    const labelFor = (value) => {
      const bar = bars.find((b) => b.dataset[attr] === value);
      const label = bar && bar.querySelector(labelSelector);
      return label ? label.textContent.trim() : value;
    };
    let selected = null;

    const apply = (value) => {
      selected = value;
      bars.forEach((bar) => {
        const on = bar.dataset[attr] === value;
        bar.classList.toggle('is-selected', on);
        bar.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      rows.forEach((row) => {
        row.hidden = value !== null && row.dataset[attr] !== value;
      });
      note.hidden = value === null;
      noteName.textContent = value === null ? '' : labelFor(value);
      summary.textContent = value === null ? defaultLabel : summaryFor(labelFor(value));
      if (value !== null) details.open = true;
    };

    bars.forEach((bar) => {
      const toggle = () => apply(selected === bar.dataset[attr] ? null : bar.dataset[attr]);
      bar.addEventListener('click', toggle);
      bar.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          toggle();
        }
      });
    });
    if (showAll) showAll.addEventListener('click', () => apply(null));
  };

  wireBarFilter({
    chartId: 'status-chart',
    detailsId: 'status-details',
    noteId: 'status-filter-note',
    showAllId: 'status-show-all',
    attr: 'status',
    summaryFor: (label) => `View ${label} locations by data source`,
  });

  wireBarFilter({
    chartId: 'multipart-chart',
    detailsId: 'multipart-details',
    noteId: 'multipart-filter-note',
    showAllId: 'multipart-show-all',
    attr: 'parts',
    summaryFor: (label) => `View geofences with ${label} by data source`,
  });

  wireBarFilter({
    chartId: 'path-issue-tiles',
    detailsId: 'path-issue-details',
    noteId: 'path-issue-filter-note',
    showAllId: 'path-issue-show-all',
    attr: 'issue',
    itemSelector: '.stat-tile',
    labelSelector: '.stat-tile-label',
    summaryFor: (label) => `View ${label.toLowerCase()}`,
  });
})();
