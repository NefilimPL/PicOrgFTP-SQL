(function registerLatestRequest(global) {
  global.PicOrg = global.PicOrg || {};

  function signatureKey(value) {
    return String(value ?? "");
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

})(window);
