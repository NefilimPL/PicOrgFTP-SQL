const test = require("node:test");
const assert = require("node:assert/strict");

global.window = { PicOrg: {} };
require("../../picorgftp_sql/web/static/runtime-status.js");

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

test("poller does not overlap and uses hidden interval", async () => {
  const calls = [];
  const pending = deferred();
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: () => {
      calls.push("fetch");
      return pending.promise;
    },
    activeIntervalMs: 5000,
    hiddenIntervalMs: 30000,
    isHidden: () => true,
  });
  const first = poller.pollNow();
  const second = poller.pollNow();
  assert.equal(calls.length, 1);
  pending.resolve({ versions: {} });
  await Promise.all([first, second]);
  assert.equal(poller.nextDelayMs(), 30000);
});

test("poller exponentially backs off failures up to sixty seconds and resets on success", async () => {
  let shouldFail = true;
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: async () => {
      if (shouldFail) throw new Error("offline");
      return { versions: {} };
    },
    activeIntervalMs: 5000,
    maxBackoffMs: 60000,
    isHidden: () => false,
  });

  await assert.rejects(poller.pollNow(), /offline/);
  assert.equal(poller.nextDelayMs(), 10000);
  await assert.rejects(poller.pollNow(), /offline/);
  assert.equal(poller.nextDelayMs(), 20000);
  await assert.rejects(poller.pollNow(), /offline/);
  assert.equal(poller.nextDelayMs(), 40000);
  await assert.rejects(poller.pollNow(), /offline/);
  assert.equal(poller.nextDelayMs(), 60000);

  shouldFail = false;
  await poller.pollNow();
  assert.equal(poller.nextDelayMs(), 5000);
});

test("poller reports only runtime versions that change after the baseline", async () => {
  const payloads = [
    {
      versions: {
        file_index: "index-1",
        process_queue: 1,
        active_clients: 2,
      },
    },
    {
      versions: {
        file_index: "index-1",
        process_queue: 1,
        active_clients: 2,
      },
    },
    {
      versions: {
        file_index: "index-2",
        process_queue: 3,
        active_clients: 2,
      },
    },
  ];
  const changes = [];
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: async () => payloads.shift(),
    onVersionChanged: (name, current, previous) => {
      changes.push([name, current, previous]);
    },
  });

  await poller.pollNow();
  await poller.pollNow();
  assert.deepEqual(changes, []);

  await poller.pollNow();
  assert.deepEqual(changes, [
    ["file_index", "index-2", "index-1"],
    ["process_queue", 3, 1],
  ]);
});

test("becoming visible cancels the hidden timer and polls immediately", async () => {
  let hidden = true;
  let visibilityHandler;
  let timerId = 0;
  const scheduled = [];
  const cleared = [];
  const timerApi = {
    setTimeout(callback, delay) {
      timerId += 1;
      scheduled.push({ callback, delay, id: timerId });
      return timerId;
    },
    clearTimeout(id) {
      cleared.push(id);
    },
  };
  const visibilityTarget = {
    addEventListener(name, callback) {
      assert.equal(name, "visibilitychange");
      visibilityHandler = callback;
    },
  };
  let calls = 0;
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: async () => {
      calls += 1;
      return { versions: {} };
    },
    isHidden: () => hidden,
    timerApi,
    visibilityTarget,
  });

  await poller.start();
  assert.equal(calls, 1);
  assert.equal(scheduled.at(-1).delay, 30000);
  const hiddenTimerId = scheduled.at(-1).id;

  hidden = false;
  visibilityHandler();
  await poller.inFlight;

  assert.deepEqual(cleared, [hiddenTimerId]);
  assert.equal(calls, 2);
  assert.equal(scheduled.at(-1).delay, 5000);
});

test("becoming hidden replaces the active timer without fetching", async () => {
  let hidden = false;
  let visibilityHandler;
  let timerId = 0;
  const scheduled = [];
  const cleared = [];
  const poller = new window.PicOrg.RuntimeStatusPoller({
    fetchStatus: async () => ({ versions: {} }),
    isHidden: () => hidden,
    timerApi: {
      setTimeout(callback, delay) {
        timerId += 1;
        scheduled.push({ callback, delay, id: timerId });
        return timerId;
      },
      clearTimeout(id) {
        cleared.push(id);
      },
    },
    visibilityTarget: {
      addEventListener(_name, callback) {
        visibilityHandler = callback;
      },
    },
  });

  await poller.start();
  const activeTimerId = scheduled.at(-1).id;
  hidden = true;
  visibilityHandler();

  assert.deepEqual(cleared, [activeTimerId]);
  assert.equal(scheduled.at(-1).delay, 30000);
});
