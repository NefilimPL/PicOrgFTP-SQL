(function registerLatestRequest(global) {
  global.PicOrg = global.PicOrg || {};
  global.PicOrg.LatestRequest = class LatestRequest {
    constructor() {
      this.controller = null;
      this.version = 0;
    }
    next() {
      if (this.controller) this.controller.abort();
      this.controller = new AbortController();
      const version = ++this.version;
      return {
        signal: this.controller.signal,
        isCurrent: () => version === this.version,
      };
    }
    cancel() {
      if (this.controller) this.controller.abort();
      this.version += 1;
    }
  };
})(window);
