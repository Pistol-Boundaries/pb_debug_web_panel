
"use strict";

// ---------- parsing ----------

// 2026-11-11 10:50:18.161 ... <+40.66299542,-73.95382831> +/- 14.25m (speed 1.53 mps / course 85.66) @ ...
const FIX_RE = /<([+-][\d.]+),([+-][\d.]+)>\s*\+\/-\s*([\d.]+)m\s*\(speed\s*([-\d.]+)/;
const TS_RE = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}\.\d{3})/;
// "1:<...>" lines are TSSingleLocationRequest samples (intermediate fixes).
const SAMPLE_RE = /^\s*\d+:\s*(?:üìç|📍)?</;

function parseLog(text) {
  const fixes = [];       // {ts, date, lat, lng, acc, speed, sample, queued, motion}
  const events = [];      // {ts, date, kind, text}
  let lastTs = null, lastDate = null, lastFix = null, pendingMotionReq = false;

  for (const line of text.split(/\r?\n/)) {
    const m = TS_RE.exec(line);
    if (m && lastDate && lastDate !== m[1]) { lastFix = null; pendingMotionReq = false; }
    if (m) { lastDate = m[1]; lastTs = m[2].slice(0, 8); }

    const f = FIX_RE.exec(line);
    if (f && lastDate) {
      const fix = {
        ts: lastTs, date: lastDate,
        lat: +f[1], lng: +f[2], acc: +f[3], speed: +f[4],
        sample: SAMPLE_RE.test(line), queued: false, motion: false,
      };
      if (![fix.lat, fix.lng, fix.acc, fix.speed].every(Number.isFinite) || Math.abs(fix.lat) > 90 || Math.abs(fix.lng) > 180) continue;
      if (pendingMotionReq && !fix.sample) { fix.motion = true; pendingMotionReq = false; }
      if (!fix.sample) lastFix = fix;
      fixes.push(fix);
      continue;
    }
    if (!lastDate) continue;

    if (line.includes("requestLocation:] [motionchange]")) pendingMotionReq = true;
    if (line.includes("TSLocationDAO insert:error:] INSERT:")) {
      if (lastFix) lastFix.queued = true;
      events.push({ ts: lastTs, date: lastDate, kind: "insert", text: "beacon point queued" });
    }
    if (line.includes("handleResponse] Response:")) {
      const code = (line.match(/Response:\s*(\d+)/) || [])[1] || "?";
      events.push({ ts: lastTs, date: lastDate, kind: /^2\d\d$/.test(code) ? "ok" : "bad",
                    text: "upload HTTP " + code });
    }
    if (line.includes("HTTP ERROR")) {
      events.push({ ts: lastTs, date: lastDate, kind: "bad",
                    text: line.replace(/^.*HTTP ERROR:?\s*/, "upload HTTP ERROR ").slice(0, 120) });
    }
    if (line.includes("TSLocationManager (build")) {
      events.push({ ts: lastTs, date: lastDate, kind: "launch", text: "app process launched" });
    }
    if (line.includes("changePace:") && line.includes("isMoving: 1")) {
      events.push({ ts: lastTs, date: lastDate, kind: "motion", text: "started moving" });
    }
  }
  return { fixes, events };
}


if (typeof module !== "undefined") module.exports = { parseLog };
