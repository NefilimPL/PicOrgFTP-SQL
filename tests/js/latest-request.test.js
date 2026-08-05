const test = require("node:test");
const assert = require("node:assert/strict");
global.window = { PicOrg: {} };
require("../../picorgftp_sql/web/static/latest-request.js");

test("next aborts the previous request and marks only latest current", () => {
  const latest = new window.PicOrg.LatestRequest();
  const first = latest.next();
  const second = latest.next();
  assert.equal(first.signal.aborted, true);
  assert.equal(first.isCurrent(), false);
  assert.equal(second.signal.aborted, false);
  assert.equal(second.isCurrent(), true);
});

test("request token rejects a changed value and context signature", () => {
  const latest = new window.PicOrg.LatestRequest();
  const token = latest.next("name\u0000ALFA\u0000STOL");

  assert.equal(token.isCurrent("name\u0000ALFA\u0000STOL"), true);
  assert.equal(token.isCurrent("name\u0000BETA\u0000SZAFA"), false);
});

test("autocomplete ignores remote results after a programmatic context change", async () => {
  const scheduled = [];
  const rendered = [];
  let requestSnapshot = { signature: "name\u0000AL", payload: { name: "AL" } };
  let resolveRemote;
  const remoteResult = new Promise((resolve) => {
    resolveRemote = resolve;
  });
  const session = new window.PicOrg.AutocompleteSession({
    captureRequest: () => requestSnapshot,
    getQuery: () => requestSnapshot.payload.name,
    isActive: () => true,
    load: () => remoteResult,
    render: (local, remote) => rendered.push({ local, remote }),
    schedule: (callback, delay) => {
      scheduled.push({ callback, delay });
      return scheduled.length;
    },
    cancelSchedule: () => {},
    delay: 180,
    limit: 80,
  });

  assert.equal(session.refresh(["ALFA"]), true);
  assert.equal(scheduled[0].delay, 180);
  const request = scheduled.shift().callback();
  requestSnapshot = { signature: "name\u0000BETA", payload: { name: "BETA" } };
  resolveRemote(["ALFABET"]);
  await request;

  assert.deepEqual(rendered, [{ local: ["ALFA"], remote: [] }]);
});

test("autocomplete skips remote work when local visible results fill the panel", () => {
  const scheduled = [];
  const rendered = [];
  let loads = 0;
  const local = Array.from({ length: 80 }, (_value, index) => `ALFA-${index}`);
  const session = new window.PicOrg.AutocompleteSession({
    captureRequest: () => ({ signature: "name\u0000ALFA", payload: { name: "ALFA" } }),
    getQuery: () => "ALFA",
    isActive: () => true,
    load: () => {
      loads += 1;
      return Promise.resolve([]);
    },
    render: (localValues, remoteValues) => rendered.push({ localValues, remoteValues }),
    schedule: (callback, delay) => {
      scheduled.push({ callback, delay });
      return scheduled.length;
    },
    cancelSchedule: () => {},
    delay: 180,
    limit: 80,
  });

  assert.equal(session.refresh(local), false);

  assert.equal(loads, 0);
  assert.deepEqual(scheduled, []);
  assert.deepEqual(rendered, [{ localValues: local, remoteValues: [] }]);
});
