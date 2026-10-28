(() => {
      const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      document.getElementById("trip-timezone").textContent = zone;
      function parseTimestamp(raw) {
        // Older saved URLs used UTC without an explicit offset.
        let value = raw.trim().replace(" ", "T");
        if (/[+-]\d{2}$/.test(value)) value += ":00";
        if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(value)) value += "Z";
        return new Date(value);
      }
      const timeFields = ["start_time", "end_time"];
      const pad = (value) => String(value).padStart(2, "0");
      timeFields.forEach((name) => {
        const raw = document.getElementById(`${name}_utc`).value;
        if (!raw) return;
        const date = parseTimestamp(raw);
        if (Number.isNaN(date.getTime())) return;
        document.getElementById(name).value = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
      });
      document.getElementById("trip-filters").addEventListener("submit", () => {
        timeFields.forEach((name) => {
          const value = document.getElementById(name).value;
          document.getElementById(`${name}_utc`).value = value ? new Date(value).toISOString() : "";
        });
      });

  // New-data pill: only for windows reaching (about) now, polled every 30s
  // while the tab is visible. Nothing reloads by itself; the pill
  // keeps the chosen start and moves the end to now.
  const pill = document.getElementById('trip-new-data');
  const endRaw = document.getElementById('end_time_utc').value;
  if (pill && endRaw && Date.now() - parseTimestamp(endRaw).getTime() < 10 * 60 * 1000) {
    const POLL_MS = 30 * 1000;
    const nouns = {map: 'point', logs: 'log', alerts: 'alert'};
    const current = new URLSearchParams(location.search);
    let lastCheck = 0;
    const check = async () => {
      if (document.hidden) return;
      lastCheck = Date.now();
      const params = new URLSearchParams({user_id: pill.dataset.user, tab: pill.dataset.tab, after: endRaw});
      ['log_type', 'alert_scope', 'platform'].forEach(name => current.getAll(name).forEach(v => params.append(name, v)));
      try {
        const response = await fetch(`/trip/new-count?${params}`, {credentials: 'same-origin'});
        if (!response.ok) return;
        const {count} = await response.json();
        if (!count) return;
        const noun = nouns[pill.dataset.tab] || 'item';
        pill.textContent = `↻ ${count > 999 ? '999+' : count} new ${noun}${count === 1 ? '' : 's'} · Show latest`;
        if (pill.hidden) {
          pill.hidden = false;
          // Next frame, so the fade-in transition runs from the hidden state.
          requestAnimationFrame(() => requestAnimationFrame(() => pill.classList.add('is-visible')));
        }
      } catch (_) { /* offline or signed out: try again next poll */ }
    };
    setInterval(check, POLL_MS);
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && Date.now() - lastCheck >= POLL_MS) check();
    });
    pill.addEventListener('click', () => {
      ['page', 'start_date', 'end_date'].forEach(name => current.delete(name));
      current.set('user_id', pill.dataset.user);
      current.set('tab', pill.dataset.tab);
      current.set('start_time', document.getElementById('start_time_utc').value);
      current.set('end_time', new Date().toISOString());
      // Fade out first; navigate once it's gone (or right away without motion).
      pill.classList.remove('is-visible');
      const go = () => { location.href = `/trip?${current}`; };
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) go();
      else setTimeout(go, 350);
    });
  }

  // Browser-local time with its zone label; UTC rides along on hover
  // (and in map popups). The raw records stay UTC.
  const formatTime = (raw, timeZone) => {
    if (!raw) return '—';
    let value = raw.replace(' ', 'T');
    if (/[+-]\d{2}$/.test(value)) value += ':00';
    if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(value)) value += 'Z';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? raw : date.toLocaleString(undefined, {timeZone, timeZoneName: 'short'});
  };
  document.querySelectorAll('[data-time]').forEach(el => {
    el.textContent = formatTime(el.dataset.time);
    if (el.dataset.time) el.title = formatTime(el.dataset.time, 'UTC');
  });
  const canvas = document.getElementById('trip-map');
  if (!canvas) return;
  if (typeof L === 'undefined') {
    canvas.textContent = 'The map could not load. Location details are still available alongside it. Reload to try again.';
    return;
  }
  const points = JSON.parse(document.getElementById('trip-points').textContent);
  const map = L.map(canvas, {preferCanvas: true});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxNativeZoom: 19, maxZoom: 23,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);
  const beacon = p => p.type === 'upload' && p.label === 'Beacon point queued';
  const tracks = new Map();
  points.forEach(p => {
    if (!p.session_id || beacon(p)) return;
    if (!tracks.has(p.session_id)) tracks.set(p.session_id, []);
    tracks.get(p.session_id).push([p.lat, p.lng]);
  });
  tracks.forEach(track => { if (track.length > 1) L.polyline(track, {color: '#2e6fbb', weight: 3}).addTo(map); });
  const markers = points.map((p, index) => {
    const popup = document.createElement('div');
    [`${index + 1}. ${p.label || p.type || 'Location'}`, formatTime(p.occurred_at), formatTime(p.occurred_at, 'UTC'), p.note,
      `${p.lat}, ${p.lng}`, `Platform: ${p.platform || 'unknown'}`, `Motion: ${p.motion_state || 'unknown'}`].filter(Boolean).forEach(text => {
      const line = document.createElement('div'); line.textContent = text; popup.appendChild(line);
    });
    return L.circleMarker([p.lat, p.lng], {
      radius: beacon(p) ? 6 : 4, color: '#fff', weight: 1, fillOpacity: .9,
      fillColor: beacon(p) ? (p.motion_state === 'still' ? '#dc2626' : '#f97316') : '#2e6fbb',
    }).addTo(map).bindPopup(popup);
  });
  const fit = () => map.fitBounds(points.map(p => [p.lat, p.lng]), {padding: [28, 28], maxZoom: 17});
  fit();
  document.getElementById('trip-fit').addEventListener('click', fit);
  document.querySelectorAll('[data-point]').forEach(button => button.addEventListener('click', () => {
    const marker = markers[Number(button.dataset.point)];
    map.setView(marker.getLatLng(), Math.max(map.getZoom(), 16)); marker.openPopup();
    document.querySelector('[data-point][aria-current]')?.removeAttribute('aria-current');
    button.setAttribute('aria-current', 'true');
  }));
})();
