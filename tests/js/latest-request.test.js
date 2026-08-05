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
