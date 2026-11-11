const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseLog} = require('../app/static/local_run_parser.js');
const fix = '<+40.66299542,-73.95382831> +/- 14.25m (speed 1.53 mps / course 85.66)';
test('normal and misencoded pins, intermediate samples, motion and queue evidence', () => {
  const result = parseLog(`2026-11-11 10:50:18.161 requestLocation:] [motionchange]
  1:📍${fix}
2026-11-11 10:50:19.161 📍${fix}
2026-11-11 10:50:20.161 TSLocationDAO insert:error:] INSERT:
2026-11-11 10:50:21.161 üìç${fix}
2026-11-11 10:50:22.161 handleResponse] Response: 204`);
  assert.equal(result.fixes.length, 3);
  assert.equal(result.fixes[0].sample, true);
  assert.equal(result.fixes[0].motion, false);
  assert.equal(result.fixes[1].motion, true);
  assert.equal(result.fixes[1].queued, true);
  assert.equal(result.fixes[2].queued, false);
  assert.equal(result.events.at(-1).kind, 'ok');
});
test('invalid coordinates, event-only logs, empty input and day boundaries', () => {
  assert.deepEqual(parseLog('unrelated text'), {fixes: [], events: []});
  const result = parseLog(`2026-11-11 10:50:18.161 ${fix}
2026-11-12 10:50:18.161 TSLocationDAO insert:error:] INSERT:
2026-11-12 10:50:19.161 <+999,-73> +/- 1m (speed 0)
2026-11-12 10:50:20.161 HTTP ERROR: <img src=x onerror=alert(1)>`);
  assert.equal(result.fixes.length, 1);
  assert.equal(result.fixes[0].queued, false);
  assert.equal(result.events.length, 2);
  assert.equal(result.events[1].kind, 'bad');
});
