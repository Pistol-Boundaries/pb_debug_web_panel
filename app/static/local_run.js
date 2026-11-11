"use strict";
if (typeof L === "undefined") {
  document.getElementById("file-status").textContent = "Map library could not load. Check your connection and reload this page.";
} else {


const map = L.map("map", { zoomControl: true });
const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19, attribution: "&copy; OpenStreetMap",
});

map.setView([39.5, -98.35], 4);
let layer = L.layerGroup().addTo(map);

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function haversine(a, b) {
  const r = 6371000, dLat = (b.lat - a.lat) * Math.PI / 180, dLng = (b.lng - a.lng) * Math.PI / 180;
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * Math.PI / 180) * Math.cos(b.lat * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(Math.min(1, h)));
}

let parsed = { fixes: [], events: [] };

function render() {
  const day = document.getElementById("day").value;
  const showRaw = document.getElementById("raws").checked;
  layer.remove();
  layer = L.layerGroup().addTo(map);

  const fixes = parsed.fixes.filter((f) => f.date === day && !f.sample);
  const events = parsed.events.filter((e) => e.date === day);

  // polyline, broken on >5 min gaps
  let seg = [], segs = [], prev = null, dist = 0;
  for (const f of fixes) {
    if (prev && (toSec(f.ts) - toSec(prev.ts) > 300)) { segs.push(seg); seg = []; }
    if (prev && seg.length) dist += haversine(prev, f);
    seg.push([f.lat, f.lng]); prev = f;
  }
  segs.push(seg);
  for (const s of segs) if (s.length > 1)
    L.polyline(s, { color: css("--raw"), weight: 3, opacity: 0.7 }).addTo(layer);

  for (const f of fixes) {
    const style = f.queued
      ? { radius: 6, color: css("--beacon"), fillColor: css("--beacon"), fillOpacity: 0.9 }
      : { radius: 3, color: css("--raw"), fillColor: css("--raw"), fillOpacity: 0.7 };
    if (!f.queued && !showRaw) continue;
    const c = L.circleMarker([f.lat, f.lng], style).addTo(layer);
    if (f.motion) c.setStyle({ color: css("--motion"), weight: 3 });
    c.bindTooltip(`${f.ts} &middot; &plusmn;${f.acc}m` +
      (f.speed >= 0 ? ` &middot; ${f.speed.toFixed(1)} m/s` : "") +
      (f.queued ? " &middot; queued" : "") + (f.motion ? " &middot; motionchange" : ""));
  }

  if (!fixes.length) map.setView([39.5, -98.35], 4);
  if (fixes.length) map.fitBounds(L.latLngBounds(fixes.map((f) => [f.lat, f.lng])), { padding: [30, 30], maxZoom: 17 });

  // stats
  const ok = events.filter((e) => e.kind === "ok").length;
  const bad = events.filter((e) => e.kind === "bad");
  const stats = {
    "fixes": fixes.length,
    "queued points": fixes.filter((f) => f.queued).length,
    "successful HTTP responses": ok,
    "upload failures": bad.length,
    "app launches": events.filter((e) => e.kind === "launch").length,
    "approx distance": (dist / 1000).toFixed(2) + " km",
    "time span": fixes.length ? `${fixes[0].ts} - ${fixes[fixes.length - 1].ts}` : "-",
  };
  document.getElementById("stats").innerHTML = Object.entries(stats)
    .map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");

  const interesting = events.filter((e) => e.kind !== "ok" && e.kind !== "insert");
  document.getElementById("events").innerHTML = interesting
    .map((e) => `<li><span class="t">${e.ts}</span><span class="${e.kind === "bad" ? "bad" : ""}">${escapeHtml(e.text)}</span></li>`)
    .join("") || "<li>none</li>";
}

const toSec = (t) => t.split(":").reduce((a, v) => a * 60 + +v, 0);

function load(text) {
  parsed = parseLog(text);
  const days = [...new Set([...parsed.fixes, ...parsed.events].map((f) => f.date))].sort();
  const sel = document.getElementById("day");
  sel.innerHTML = days.map((d) => `<option>${d}</option>`).join("");
  sel.value = days[days.length - 1] || "";
  
  render();
}

// Read files locally; never submit their contents to the server.
let loadId = 0;
async function readFile(file) {
  if (!file) return;
  const id = ++loadId;
  const status = document.getElementById("file-status");
  status.textContent = `Reading ${file.name}…`;
  try {
    const text = await file.text();
    if (id !== loadId) return;
    load(text);
    status.textContent = `${file.name} · ${parsed.fixes.filter(f => !f.sample).length} fixes · ${parsed.events.length} events` +
      (!parsed.fixes.length ? " · No supported location fixes found. Choose a TransistorSoft diagnostic text log." : "");
  } catch (error) {
    if (id === loadId) status.textContent = "Could not read this file. Try selecting it again.";
  }
}
document.getElementById("file").addEventListener("change", e => readFile(e.target.files[0]));
window.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("drop", e => {
  e.preventDefault();
  readFile(e.dataTransfer.files[0]);
});
document.getElementById("day").addEventListener("change", render);
document.getElementById("raws").addEventListener("change", render);
document.getElementById("basemap").addEventListener("change", e => {
  if (e.target.checked) tiles.addTo(map); else tiles.remove();
});
render();

}
