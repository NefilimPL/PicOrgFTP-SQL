(function registerLatestRequest(global) {
  global.PicOrg = global.PicOrg || {};

  function signatureKey(value) {
    return String(value ?? "");
  }

  function visibleLocalCount(values, query, limit) {
    const needle = String(query || "").trim().toUpperCase();
    const seen = new Set();
    let count = 0;
    for (const value of values || []) {
      const text = String(value || "").trim();
      const key = text.toUpperCase();
      if (!text || seen.has(key) || (needle && !key.includes(needle))) continue;
      seen.add(key);
      count += 1;
      if (count >= limit) return count;
    }
    return count;
  }

  global.PicOrg.LatestRequest = class LatestRequest {
    constructor() {
      this.controller = null;
      this.version = 0;
    }
    next(signature = "") {
      if (this.controller) this.controller.abort();
      this.controller = new AbortController();
      const version = ++this.version;
      const requestSignature = signatureKey(signature);
      return {
        signal: this.controller.signal,
        isCurrent: (currentSignature = requestSignature) =>
          version === this.version &&
          requestSignature === signatureKey(currentSignature),
      };
    }
    cancel() {
      if (this.controller) this.controller.abort();
      this.version += 1;
    }
  };

  global.PicOrg.AutocompleteSession = class AutocompleteSession {
    constructor({
      captureRequest,
      getQuery,
      isActive,
      load,
      render,
      schedule,
      cancelSchedule,
      delay = 180,
      limit = 80,
    }) {
      this.captureRequest = captureRequest;
      this.getQuery = getQuery;
      this.isActive = isActive;
      this.load = load;
      this.render = render;
      this.schedule = schedule;
      this.cancelSchedule = cancelSchedule;
      this.delay = Math.max(0, Number(delay) || 0);
      this.limit = Math.max(1, Number(limit) || 1);
      this.latest = new global.PicOrg.LatestRequest();
      this.timer = null;
    }

    clearTimer() {
      if (this.timer === null) return;
      this.cancelSchedule(this.timer);
      this.timer = null;
    }

    refresh(localValues) {
      const local = Array.isArray(localValues) ? localValues : [];
      this.render(local, []);
      this.clearTimer();

      if (visibleLocalCount(local, this.getQuery(), this.limit) >= this.limit) {
        this.latest.cancel();
        return false;
      }

      const request = this.captureRequest();
      const token = this.latest.next(request.signature);
      this.timer = this.schedule(() => {
        this.timer = null;
        return Promise.resolve(this.load(request, token.signal))
          .then((remoteValues) => {
            const current = this.captureRequest();
            if (!token.isCurrent(current.signature) || !this.isActive()) return;
            this.render(
              local,
              Array.isArray(remoteValues) ? remoteValues : [],
            );
          })
          .catch((error) => {
            if (error && error.name === "AbortError") return;
          });
      }, this.delay);
      return true;
    }

    cancel() {
      this.clearTimer();
      this.latest.cancel();
    }
  };
})(window);
