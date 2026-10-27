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
