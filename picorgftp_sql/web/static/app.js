const state = {
  slots: [],
  files: new Map(),
  filePreviewUrls: new Map(),
  loadedPhotos: new Map(),
  deletedSlots: new Map(),
  lists: {},
  entries: [],
  selectedList: "names",
  settings: null,
  currentUser: null,
  isAdmin: false,
  fileIndex: null,
  photosLoading: false,
  loadedEntryOriginal: null,
  slotFits: new Map(),
  defaultSlotFit: false,
  slotSources: new Map(),
  draggedSlotPrefix: "",
  lastLookupMs: null,
  activeSettingsTab: "app",
  history: null,
  historyPage: 1,
  historyPageSize: 50,
  historySearchTimer: 0,
  pimcoreTestOperation: null,
  pimcoreLookupTimer: 0,
  pimcoreLookupRequestId: 0,
  pimcoreLastCheckedEan: "",
  pimcoreMissingEan: "",
  pimcoreCreateSchema: [],
  pimcoreRuntimeEnabled: false,
  pimcoreExistingObject: null,
  pimcoreEditObjectId: 0,
  pimcoreEditRequestId: 0,
  pimcoreEditMarker: "",
  pimcoreEditSchema: [],
  pimcoreTemplateRow: null,
  pimcoreSetup: {
    step: 1,
    settings: null,
    classes: [],
    folders: [],
    fields: [],
    mappings: [],
    manualLocation: false,
    eanTarget: "",
    report: null,
  },
  pimcoreSetupPrompted: false,
  logs: null,
  settingsSecrets: null,
  theme: localStorage.getItem("picorg-theme") || "light",
  suppressAutoSearch: false,
  lastAutoSearchKey: "",
  photoLoadRequestId: 0,
  photoSourceStatus: new Map(),
  listFilter: "",
  declinedListPrompts: new Set(),
  activeListPromptKeys: new Set(),
  productFields: {},
  ftpPreviewLoading: new Set(),
  ftpPreviewBackgroundLoading: new Set(),
  ftpPreviewCache: new Map(),
  backgroundFtpPreviewTimer: 0,
  backgroundFtpPreviewLimit: 1,
  photoSourcesLoaded: new Set(),
  ftpEnabled: true,
  backgroundFtpLookupTimer: 0,
  backgroundFtpLookupKey: "",
  backgroundFtpLookupRequestId: 0,
  processing: {},
  security: {},
  slotRevisions: new Map(),
  userSelectedSlotSources: new Set(),
  slotUploadRequestId: 0,
  processStatusTimer: 0,
  processStatusStartedAt: 0,
  navigationGuardBypass: false,
  webImages: [],
  webImageSelected: new Set(),
  webImagePageUrl: "",
  webImageScanMode: ["links", "metadata"].includes(
    localStorage.getItem("picorg-web-image-scan-mode")
  )
    ? localStorage.getItem("picorg-web-image-scan-mode")
    : "links",
  webImageCache: new Map(),
  webImageCacheQueue: [],
  webImageCacheActive: 0,
  processJobs: new Map(),
  processJobPollTimer: 0,
  processQueue: { jobs: [], active_count: 0, queued_count: 0, current: null },
  acknowledgedProcessAlerts: new Set(),
  activeUsers: [],
  activeUsersEnabled: false,
  activePresenceClientId: "",
  csrfToken: "",
  pollers: [],
};

const WEB_IMAGE_CACHE_LIMIT = 2;
const MAX_AUTOCOMPLETE_OPTIONS = 80;
const ACTIVE_USERS_VISIBLE_LIMIT = 5;
const CSRF_HEADER = "X-PicOrg-CSRF";
const CLIENT_ID_HEADER = "X-PicOrg-Client-Id";
const CSRF_SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const SECRET_REVEAL_MS = 60000;
const POLL_HIDDEN_DELAY_MS = 30000;
const SQLITE_BACKUP_DAYS = [
  ["mon", "Pon"],
  ["tue", "Wt"],
  ["wed", "Sr"],
  ["thu", "Czw"],
  ["fri", "Pt"],
  ["sat", "Sob"],
  ["sun", "Nd"],
];
const CLIENT_EXECUTABLE_UPLOAD_EXTENSIONS = new Set([
  "exe",
  "bat",
  "cmd",
  "com",
  "msi",
  "ps1",
  "vbs",
  "js",
  "jar",
  "dll",
  "scr",
  "pif",
  "sh",
]);

const listLabels = {
  names: "Nazwy",
  types: "Typy",
  models: "Modele",
  colors: "Kolory",
  extras: "Dodatki",
};

const photoSourceLabels = {
  local: "lokalne",
  sql: "SQL",
  ftp: "FTP",
  all: "dane",
};

const processStatusLabels = {
  queued: "Oczekuje",
  running: "Trwa",
  completed: "Zakonczone",
  failed: "Blad",
};

const slotGrid = document.querySelector("#slotGrid");
const slotTemplate = document.querySelector("#slotTemplate");
const processQueuePanel = document.querySelector("#processQueuePanel");
const processQueueSummary = document.querySelector("#processQueueSummary");
const processQueueList = document.querySelector("#processQueueList");
const productForm = document.querySelector("#productForm");
const formStatus = document.querySelector("#formStatus");
const resultOutput = document.querySelector("#resultOutput");
const resultMeta = document.querySelector("#resultMeta");
const resultSection = document.querySelector(".result-section");
const slotCount = document.querySelector("#slotCount");
const fileIndexInfo = document.querySelector("#fileIndexInfo");
const latencyInfo = document.querySelector("#latencyInfo");
const serverInfo = document.querySelector("#serverInfo");
const versionInfo = document.querySelector("#versionInfo");
const submitButton = document.querySelector("#submitButton");
const clearButton = document.querySelector("#clearButton");
const logoutButton = document.querySelector("#logoutButton");
const themeToggleButton = document.querySelector("#themeToggleButton");
const entrySelect = document.querySelector("#entrySelect");
const findByEanButton = document.querySelector("#findByEanButton");
const findProductButton = document.querySelector("#findProductButton");
const pimcoreEditButton = document.querySelector("#pimcoreEditButton");
const webImagesButton = document.querySelector("#webImagesButton");
const activeUsersPresence = document.querySelector("#activeUsersPresence");
const activeUsersList = document.querySelector("#activeUsersList");
const activeUsersMoreButton = document.querySelector("#activeUsersMoreButton");
const activeUsersPopover = document.querySelector("#activeUsersPopover");
const webImageUrl = document.querySelector("#webImageUrl");
const scanWebImagesButton = document.querySelector("#scanWebImagesButton");
const webImagesModal = document.querySelector("#webImagesModal");
const webImagesStatus = document.querySelector("#webImagesStatus");
const webImagesOutput = document.querySelector("#webImagesOutput");
const webImageScanMode = document.querySelector("#webImageScanMode");
const webImageMinWidth = document.querySelector("#webImageMinWidth");
const webImageMinHeight = document.querySelector("#webImageMinHeight");
const webImageMinKb = document.querySelector("#webImageMinKb");
const webImageUrlFilter = document.querySelector("#webImageUrlFilter");
const webImageHideThumbnails = document.querySelector("#webImageHideThumbnails");
const browserExtensionDownload = document.querySelector("#browserExtensionDownload");
const browserExtensionHelpButton = document.querySelector("#browserExtensionHelpButton");
const browserExtensionHelp = document.querySelector("#browserExtensionHelp");
const browserExtensionReceiveButton = document.querySelector("#browserExtensionReceiveButton");
const webImagesSelectVisibleButton = document.querySelector("#webImagesSelectVisibleButton");
const webImagesClearSelectionButton = document.querySelector("#webImagesClearSelectionButton");
const webImagesClearDataButton = document.querySelector("#webImagesClearDataButton");
const webImagesAddButton = document.querySelector("#webImagesAddButton");
const listTabs = document.querySelector("#listTabs");
const listValues = document.querySelector("#listValues");
const listAddForm = document.querySelector("#listAddForm");
const listAddInput = document.querySelector("#listAddInput");
const listStatus = document.querySelector("#listStatus");
const listUsageTitle = document.querySelector("#listUsageTitle");
const listUsageOutput = document.querySelector("#listUsageOutput");
const settingsOutput = document.querySelector("#settingsOutput");
const settingsStatus = document.querySelector("#settingsStatus");
const entryMatches = document.querySelector("#entryMatches");
const historyUserFilter = document.querySelector("#historyUserFilter");
const historySearchInput = document.querySelector("#historySearchInput");
const historyRefreshButton = document.querySelector("#historyRefreshButton");
const historyPrevButton = document.querySelector("#historyPrevButton");
const historyNextButton = document.querySelector("#historyNextButton");
const historyPageInfo = document.querySelector("#historyPageInfo");
const historyOutput = document.querySelector("#historyOutput");
const historyDetailTitle = document.querySelector("#historyDetailTitle");
const historyDetailOutput = document.querySelector("#historyDetailOutput");
const historyTimingTitle = document.querySelector("#historyTimingTitle");
const historyTimingOutput = document.querySelector("#historyTimingOutput");
const pimcoreTestModal = document.querySelector("#pimcoreTestModal");
const pimcoreTestForm = document.querySelector("#pimcoreTestForm");
const pimcoreLiveLog = document.querySelector("#pimcoreLiveLog");
const pimcoreTestElapsed = document.querySelector("#pimcoreTestElapsed");
const pimcoreTestStatus = document.querySelector("#pimcoreTestStatus");
const pimcoreTestSubmitButton = document.querySelector("#pimcoreTestSubmitButton");
const pimcoreTestRegenerateButton = document.querySelector("#pimcoreTestRegenerateButton");
const pimcoreTestClearButton = document.querySelector("#pimcoreTestClearButton");
const pimcoreTestCloseButton = document.querySelector("#pimcoreTestCloseButton");
const pimcoreTemplateModal = document.querySelector("#pimcoreTemplateModal");
const pimcoreTemplateTarget = document.querySelector("#pimcoreTemplateTarget");
const pimcoreTemplateText = document.querySelector("#pimcoreTemplateText");
const pimcoreTemplateSqlControls = document.querySelector("#pimcoreTemplateSqlControls");
const pimcoreTemplateSources = document.querySelector("#pimcoreTemplateSources");
const pimcoreTemplateFunctions = document.querySelector("#pimcoreTemplateFunctions");
const pimcoreTemplateTranslate = document.querySelector("#pimcoreTemplateTranslate");
const pimcoreTemplateLanguage = document.querySelector("#pimcoreTemplateLanguage");
const pimcoreTemplatePreview = document.querySelector("#pimcoreTemplatePreview");
const pimcoreTemplateStatus = document.querySelector("#pimcoreTemplateStatus");
const pimcoreTemplatePreviewButton = document.querySelector("#pimcoreTemplatePreviewButton");
const pimcoreTemplateSaveButton = document.querySelector("#pimcoreTemplateSaveButton");
const pimcoreTemplateClearButton = document.querySelector("#pimcoreTemplateClearButton");
const pimcoreTemplateCancelButton = document.querySelector("#pimcoreTemplateCancelButton");
const pimcoreHistoryModal = document.querySelector("#pimcoreHistoryModal");
const pimcoreHistoryFilters = document.querySelector("#pimcoreHistoryFilters");
const pimcoreHistoryOutput = document.querySelector("#pimcoreHistoryOutput");
const pimcoreHistoryCloseButton = document.querySelector("#pimcoreHistoryCloseButton");
const pimcoreHistoryExportCsvButton = document.querySelector("#pimcoreHistoryExportCsvButton");
const pimcoreHistoryExportJsonButton = document.querySelector("#pimcoreHistoryExportJsonButton");
const pimcoreMissingModal = document.querySelector("#pimcoreMissingModal");
const pimcoreMissingMessage = document.querySelector("#pimcoreMissingMessage");
const pimcoreMissingCreateButton = document.querySelector("#pimcoreMissingCreateButton");
const pimcoreMissingContinueButton = document.querySelector("#pimcoreMissingContinueButton");
const pimcoreMissingCancelButton = document.querySelector("#pimcoreMissingCancelButton");
const pimcoreCreateModal = document.querySelector("#pimcoreCreateModal");
const pimcoreCreateForm = document.querySelector("#pimcoreCreateForm");
const pimcoreCreateSubmitButton = document.querySelector("#pimcoreCreateSubmitButton");
const pimcoreCreateCancelButton = document.querySelector("#pimcoreCreateCancelButton");
const pimcoreCreateStatus = document.querySelector("#pimcoreCreateStatus");
const pimcoreEditModal = document.querySelector("#pimcoreEditModal");
const pimcoreEditForm = document.querySelector("#pimcoreEditForm");
const pimcoreEditSubmitButton = document.querySelector("#pimcoreEditSubmitButton");
const pimcoreEditRecalculateAllButton = document.querySelector("#pimcoreEditRecalculateAllButton");
const pimcoreEditCancelButton = document.querySelector("#pimcoreEditCancelButton");
const pimcoreEditStatus = document.querySelector("#pimcoreEditStatus");
const pimcoreEditObjectInfo = document.querySelector("#pimcoreEditObjectInfo");
const pimcoreSetupModal = document.querySelector("#pimcoreSetupModal");
const pimcoreSetupForm = document.querySelector("#pimcoreSetupForm");
const pimcoreSetupStepTitle = document.querySelector("#pimcoreSetupStepTitle");
const pimcoreSetupBody = document.querySelector("#pimcoreSetupBody");
const pimcoreSetupProgress = document.querySelector("#pimcoreSetupProgress");
const pimcoreSetupBackButton = document.querySelector("#pimcoreSetupBackButton");
const pimcoreSetupNextButton = document.querySelector("#pimcoreSetupNextButton");
const pimcoreSetupCancelButton = document.querySelector("#pimcoreSetupCancelButton");
const pimcoreSetupStatus = document.querySelector("#pimcoreSetupStatus");
const backupHistoryOutput = document.querySelector("#backupHistoryOutput");
const backupDiffOutput = document.querySelector("#backupDiffOutput");
const logsRefreshButton = document.querySelector("#logsRefreshButton");
const logsClearButton = document.querySelector("#logsClearButton");
const logsClearForm = document.querySelector("#logsClearForm");
const logsClearPassword = document.querySelector("#logsClearPassword");
const logsClearStatus = document.querySelector("#logsClearStatus");
const logsOutput = document.querySelector("#logsOutput");
const logsButton = document.querySelector('[data-modal="logs"]');
const secretRevealModal = document.querySelector("#secretRevealModal");
const secretRevealForm = document.querySelector("#secretRevealForm");
const secretRevealPassword = document.querySelector("#secretRevealPassword");
const secretRevealStatus = document.querySelector("#secretRevealStatus");
const processAlertModal = document.querySelector("#processAlertModal");
const processAlertTitle = document.querySelector("#processAlertTitle");
const processAlertMessage = document.querySelector("#processAlertMessage");
const processAlertEntry = document.querySelector("#processAlertEntry");
const processAlertLoadButton = document.querySelector("#processAlertLoadButton");

function isSameOriginRequest(path) {
  try {
    return new URL(path, window.location.href).origin === window.location.origin;
  } catch (_error) {
    return true;
  }
}

function isMutatingRequest(options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  return !CSRF_SAFE_METHODS.has(method);
}

function activePresenceClientId() {
  if (state.activePresenceClientId) {
    return state.activePresenceClientId;
  }
  const key = "picorg-active-presence-client-id";
  try {
    const stored = sessionStorage.getItem(key);
    if (stored) {
      state.activePresenceClientId = stored;
      return stored;
    }
  } catch (_error) {
    // Session storage can be disabled; keep the generated ID in memory for this page.
  }
  const generated =
    window.crypto?.randomUUID?.() ||
    `client-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  state.activePresenceClientId = generated;
  try {
    sessionStorage.setItem(key, generated);
  } catch (_error) {
    // In-memory ID is enough when storage is unavailable.
  }
  return generated;
}

function applyClientIdentityHeader(path, fetchOptions) {
  if (!isSameOriginRequest(path)) {
    return;
  }
  const clientId = activePresenceClientId();
  if (!clientId) {
    return;
  }
  const headers = new Headers(fetchOptions.headers || {});
  headers.set(CLIENT_ID_HEADER, clientId);
  fetchOptions.headers = headers;
}

function applyPanelRequestHeaders(path, fetchOptions) {
  if (!isMutatingRequest(fetchOptions) || !isSameOriginRequest(path)) {
    return;
  }
  const headers = new Headers(fetchOptions.headers || {});
  headers.set("X-Requested-With", "XMLHttpRequest");
  if (state.csrfToken) {
    headers.set(CSRF_HEADER, state.csrfToken);
  }
  fetchOptions.headers = headers;
}

async function requestJson(path, options = {}) {
  const timeoutMs = Number(options.timeoutMs || 0);
  const fetchOptions = { ...options };
  delete fetchOptions.timeoutMs;
  applyClientIdentityHeader(path, fetchOptions);
  applyPanelRequestHeaders(path, fetchOptions);
  let timeoutId = 0;
  if (timeoutMs > 0 && !fetchOptions.signal) {
    const controller = new AbortController();
    fetchOptions.signal = controller.signal;
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  let response;
  try {
    response = await fetch(path, fetchOptions);
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(
        `Backend nie odpowiedzial w ciagu ${Math.round(timeoutMs / 1000)} s (${path}). ` +
          "Jesli podales folder sieciowy albo dysk mapowany, sprawdz dostep backendu do tej lokalizacji."
      );
    }
    throw new Error(
      `Nie udalo sie polaczyc z backendem (${path}). Sprawdz, czy serwer web dziala. Szczegoly: ${
        error.message || error
      }`
    );
  } finally {
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = "/login";
    }
    const detail = payload.detail;
    const message =
      typeof detail === "string" ? detail : detail?.message || "Operacja nie powiodla sie.";
    const error = new Error(message);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  if (payload.csrf_token) {
    state.csrfToken = payload.csrf_token;
  }
  return payload;
}

function updateAdminUi() {
  state.isAdmin = state.currentUser?.role === "admin";
  document.querySelectorAll(".admin-only").forEach((node) => {
    node.hidden = !state.isAdmin;
  });
  if (!state.isAdmin) {
    updateLogAlert({});
  }
}

function setActiveModalNav(name = "") {
  document.querySelectorAll("[data-modal]").forEach((button) => {
    button.classList.toggle("active", button.dataset.modal === name);
  });
}

function applyTheme() {
  document.body.dataset.theme = state.theme;
  if (themeToggleButton) {
    themeToggleButton.textContent = state.theme === "dark" ? "Jasny" : "Ciemny";
  }
  localStorage.setItem("picorg-theme", state.theme);
}

function openModal(name) {
  if (!name) {
    return;
  }
  if ((name === "settings" || name === "logs") && !state.isAdmin) {
    formStatus.textContent = "Ten widok jest dostepny tylko dla administratora.";
    return;
  }
  closeAutocompletePanels();
  document.querySelector(`#${name}View`)?.classList.add("active");
  document.querySelector(`#${name}Modal`)?.classList.add("active");
  setActiveModalNav(name);
  if (name === "settings") {
    loadSettings().catch((error) => {
      settingsStatus.textContent = error.message;
    });
  }
  if (name === "history") {
    loadHistory().catch(showHistoryLoadError);
  }
  if (name === "logs") {
    loadLogs().catch((error) => {
      logsOutput.textContent = error.message;
    });
  }
}

function closeModals() {
  document.querySelectorAll(".modal-view").forEach((modal) => modal.classList.remove("active"));
  if (logsClearPassword) logsClearPassword.value = "";
  if (logsClearStatus) logsClearStatus.textContent = "";
  closeSecretRevealModal();
  toggleActiveUsersPopover(false);
  setActiveModalNav("");
}

function activeUserLastSeenLabel(user = {}) {
  const text = String(user.last_seen || "").trim();
  return text ? `Ostatnio: ${text}` : "Aktywny";
}

function toggleActiveUsersPopover(force) {
  if (!activeUsersPopover || !activeUsersMoreButton) {
    return;
  }
  const nextOpen = force === undefined ? activeUsersPopover.hidden : Boolean(force);
  activeUsersPopover.hidden = !nextOpen;
  activeUsersMoreButton.setAttribute("aria-expanded", nextOpen ? "true" : "false");
}

function renderActiveUsersPresence(payload = {}) {
  if (!activeUsersPresence || !activeUsersList || !activeUsersMoreButton || !activeUsersPopover) {
    return;
  }
  const users = Array.isArray(payload.users) ? payload.users : [];
  const enabled = Boolean(payload.enabled);
  state.activeUsersEnabled = enabled;
  state.activeUsers = users;
  activeUsersList.textContent = "";
  activeUsersPopover.textContent = "";
  const visibleUsers = users.slice(0, ACTIVE_USERS_VISIBLE_LIMIT);
  activeUsersPresence.hidden = !enabled || !users.length;
  activeUsersMoreButton.hidden = users.length <= ACTIVE_USERS_VISIBLE_LIMIT;
  if (activeUsersMoreButton.hidden) {
    toggleActiveUsersPopover(false);
  }
  if (!enabled || !users.length) {
    toggleActiveUsersPopover(false);
    return;
  }
  for (const user of visibleUsers) {
    const label = document.createElement("span");
    const dot = document.createElement("span");
    const name = document.createElement("span");
    label.className = "presence-user-label";
    dot.className = "presence-user-dot";
    dot.setAttribute("aria-hidden", "true");
    name.textContent = String(user.username || "");
    label.title = activeUserLastSeenLabel(user);
    label.append(dot, name);
    activeUsersList.appendChild(label);
  }
  for (const user of users) {
    const row = document.createElement("div");
    const name = document.createElement("strong");
    const seen = document.createElement("span");
    row.className = "active-users-popover-row";
    name.textContent = String(user.username || "");
    seen.textContent = activeUserLastSeenLabel(user);
    row.append(name, seen);
    activeUsersPopover.appendChild(row);
  }
}

async function refreshActiveUsersPresence() {
  const payload = await requestJson("/api/server/presence");
  renderActiveUsersPresence(payload);
}

function notifyActiveUsersPresenceLeave() {
  const clientId = activePresenceClientId();
  if (!clientId) {
    return;
  }
  const headers = {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    [CLIENT_ID_HEADER]: clientId,
  };
  if (state.csrfToken) {
    headers[CSRF_HEADER] = state.csrfToken;
  }
  fetch("/api/server/presence/leave", {
    method: "POST",
    headers,
    body: "{}",
    keepalive: true,
  }).catch(() => {});
}

function slotFileItem(value) {
  if (!value) return null;
  if (value.file || value.token || value.uploading || value.error) return value;
  return {
    file: value,
    name: value.name || "",
    size: Number(value.size || 0),
    type: value.type || "",
    token: "",
    url: "",
    thumb_url: "",
    file_version: "",
    preprocessed: false,
    cache_timing: null,
    client_preprocess_ms: 0,
    progress: 0,
    uploading: false,
    error: "",
  };
}

function slotFileObject(value) {
  return slotFileItem(value)?.file || null;
}

function slotFileName(value) {
  const item = slotFileItem(value);
  return item?.name || item?.file?.name || "plik";
}

function slotFileSize(value) {
  const item = slotFileItem(value);
  return Number(item?.size || item?.file?.size || 0);
}

function slotFileType(value) {
  const item = slotFileItem(value);
  return item?.type || item?.file?.type || "";
}

function slotFileToken(value) {
  return String(slotFileItem(value)?.token || "").trim();
}

function slotUploadProgress(value) {
  const progress = Number(slotFileItem(value)?.progress || 0);
  return Math.max(0, Math.min(100, Math.round(progress)));
}

function isSlotUploadActive(value) {
  return Boolean(slotFileItem(value)?.uploading);
}

function slotUploadError(value) {
  return String(slotFileItem(value)?.error || "").trim();
}

function fileLabel(file) {
  const item = slotFileItem(file);
  if (!item) {
    return "Brak pliku";
  }
  const kb = Math.max(1, Math.round(slotFileSize(item) / 1024));
  const base = `${slotFileName(item)} (${kb} KB)`;
  if (slotUploadError(item)) return `${base} - blad uploadu: ${slotUploadError(item)}`;
  if (isSlotUploadActive(item)) return `${base} - wysylanie ${slotUploadProgress(item)}%`;
  if (slotFileToken(item)) return `${base} - w cache`;
  return base;
}

function formatDuration(ms) {
  const value = Math.max(0, Number(ms || 0));
  if (value < 1000) return `${Math.round(value)} ms`;
  if (value < 10000) return `${(value / 1000).toFixed(2)} s`;
  return `${(value / 1000).toFixed(1)} s`;
}

function formatFileSize(bytes) {
  const value = Math.max(0, Number(bytes || 0));
  if (value < 1024) return `${Math.round(value)} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function webImageDimensions(image) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  return width && height ? `${width} x ${height}` : "rozmiar nieznany";
}

function webImageFilters() {
  return {
    minWidth: Math.max(0, Number(webImageMinWidth?.value || 0)),
    minHeight: Math.max(0, Number(webImageMinHeight?.value || 0)),
    minKb: Math.max(0, Number(webImageMinKb?.value || 0)),
    urlFilter: String(webImageUrlFilter?.value || "").trim(),
    hideThumbnails: Boolean(webImageHideThumbnails?.checked),
  };
}

function isThumbnailWebImage(image) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  return image?.kind === "thumbnail" || (width > 0 && height > 0 && Math.max(width, height) < 300);
}

function parseWebImageUrlFilter(text) {
  const parsed = { include: [], exclude: [] };
  const matches = String(text || "").toLowerCase().match(/!?<[^>]+>|[^\s,;]+/g) || [];
  for (let part of matches) {
    part = part.trim();
    if (!part) continue;
    let target = parsed.include;
    if (part.startsWith("!") && part.length > 1) {
      target = parsed.exclude;
      part = part.slice(1);
    }
    const terms =
      part.startsWith("<") && part.endsWith(">")
        ? part
            .slice(1, -1)
            .split("|")
            .map((term) => term.trim())
            .filter(Boolean)
        : [part];
    if (terms.length) target.push(terms);
  }
  return parsed;
}

function webImageMatchesUrlFilter(image, text) {
  const parsed = parseWebImageUrlFilter(text);
  const haystack = `${image?.url || ""} ${image?.filename || ""} ${image?.source || ""}`.toLowerCase();
  if (parsed.exclude.some((group) => group.some((term) => haystack.includes(term)))) return false;
  if (parsed.include.some((group) => !group.some((term) => haystack.includes(term)))) return false;
  return true;
}

function webImagePassesFilters(image, filters = webImageFilters()) {
  const width = Number(image?.width || 0);
  const height = Number(image?.height || 0);
  const kb = Number(image?.size_bytes || 0) / 1024;
  const unknownPasses = state.webImageScanMode === "links";
  if (!webImageMatchesUrlFilter(image, filters.urlFilter)) return false;
  if (filters.minWidth && width && width < filters.minWidth) return false;
  if (filters.minWidth && !width && !unknownPasses) return false;
  if (filters.minHeight && height && height < filters.minHeight) return false;
  if (filters.minHeight && !height && !unknownPasses) return false;
  if (filters.minKb && kb && kb < filters.minKb) return false;
  if (filters.minKb && !kb && !unknownPasses) return false;
  if (filters.hideThumbnails && isThumbnailWebImage(image)) return false;
  return true;
}

function visibleWebImageEntries() {
  const filters = webImageFilters();
  return (state.webImages || [])
    .map((image, index) => ({ image, index }))
    .filter((entry) => webImagePassesFilters(entry.image, filters));
}

function webImageCacheKey(image) {
  return String(image?.url || "").trim();
}

function webImageCacheEntry(image) {
  return state.webImageCache.get(webImageCacheKey(image)) || null;
}

function webImageCacheLabel(image) {
  const entry = webImageCacheEntry(image);
  if (!entry) return "";
  if (entry.status === "queued") return "oczekuje";
  if (entry.status === "loading") return "pobieranie";
  if (entry.status === "ready") return "w cache";
  if (entry.status === "error") return "blad cache";
  return "";
}

function queueWebImageCache(image, prefix = "web", { retry = false, render = true } = {}) {
  const key = webImageCacheKey(image);
  if (!key) return null;
  const existing = state.webImageCache.get(key);
  if (existing && existing.status !== "error") return existing;
  if (existing && existing.status === "error" && !retry) return existing;
  const entry = {
    status: "queued",
    payload: null,
    error: "",
    promise: null,
  };
  state.webImageCache.set(key, entry);
  state.webImageCacheQueue.push({ key, image, prefix });
  pumpWebImageCacheQueue();
  if (render) {
    renderWebImagesPicker();
  }
  return entry;
}

function pumpWebImageCacheQueue() {
  while (state.webImageCacheActive < WEB_IMAGE_CACHE_LIMIT && state.webImageCacheQueue.length) {
    const task = state.webImageCacheQueue.shift();
    const entry = state.webImageCache.get(task.key);
    if (!entry || entry.status !== "queued") continue;
    state.webImageCacheActive += 1;
    entry.status = "loading";
    entry.promise = cacheWebImageForSlot(task.image, task.prefix)
      .then((payload) => {
        entry.status = "ready";
        entry.payload = payload;
        entry.error = "";
        return payload;
      })
      .catch((error) => {
        entry.status = "error";
        entry.error = error.message || String(error);
        throw error;
      })
      .finally(() => {
        state.webImageCacheActive = Math.max(0, state.webImageCacheActive - 1);
        renderWebImagesPicker();
        pumpWebImageCacheQueue();
      });
    entry.promise.catch(() => {});
    renderWebImagesPicker();
  }
}

async function cachedWebImagePayload(image, prefix) {
  let entry = webImageCacheEntry(image);
  if (!entry || entry.status === "error") {
    entry = queueWebImageCache(image, prefix, { retry: true });
  }
  if (!entry) {
    throw new Error("Nie udalo sie przygotowac cache zdjecia.");
  }
  if (entry.payload) {
    return entry.payload;
  }
  if (entry.promise) {
    return entry.promise;
  }
  pumpWebImageCacheQueue();
  if (entry.promise) {
    return entry.promise;
  }
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (entry.payload) {
        window.clearInterval(timer);
        resolve(entry.payload);
      } else if (entry.status === "error") {
        window.clearInterval(timer);
        reject(new Error(entry.error || "Nie udalo sie pobrac zdjecia."));
      } else if (Date.now() - started > 60000) {
        window.clearInterval(timer);
        reject(new Error("Przekroczono czas oczekiwania na pobranie zdjecia."));
      }
    }, 200);
  });
}

function openWebImagesModal() {
  webImagesModal?.classList.add("active");
  webImageUrl?.focus();
}

function closeWebImagesModal() {
  webImagesModal?.classList.remove("active");
}

function clearLoadedWebImages() {
  state.webImages = [];
  state.webImageSelected.clear();
  state.webImagePageUrl = "";
  state.webImageCache.clear();
  state.webImageCacheQueue = [];
  state.webImageCacheActive = 0;
  if (webImagesStatus) {
    webImagesStatus.textContent = "";
  }
  if (webImagesOutput) {
    webImagesOutput.textContent = "Brak pobranych zdjec.";
    webImagesOutput.classList.add("empty-state");
  }
  formStatus.textContent = "Wyczyszczono wczytane zdjecia WWW.";
}

function renderWebImagesPicker() {
  if (!webImagesOutput) return;
  const visible = visibleWebImageEntries();
  const selectedVisible = visible.filter((entry) => state.webImageSelected.has(entry.index)).length;
  if (webImagesStatus) {
    webImagesStatus.textContent = `${selectedVisible}/${visible.length} zaznaczonych, ${state.webImages.length} wykrytych`;
  }
  webImagesOutput.textContent = "";
  webImagesOutput.classList.toggle("empty-state", !visible.length);
  if (!visible.length) {
    webImagesOutput.textContent = state.webImages.length
      ? "Filtry ukryly wszystkie zdjecia."
      : "Brak pobranych zdjec.";
    return;
  }
  for (const { image, index } of visible) {
    const card = document.createElement("article");
    const preview = document.createElement("div");
    const img = document.createElement("img");
    const checkbox = document.createElement("input");
    const meta = document.createElement("div");
    const title = document.createElement("strong");
    const dimensions = document.createElement("span");
    const size = document.createElement("span");
    const format = document.createElement("span");
    const source = document.createElement("span");
    const cache = document.createElement("span");
    checkbox.type = "checkbox";
    checkbox.checked = state.webImageSelected.has(index);
    checkbox.setAttribute("aria-label", `Wybierz obraz ${image.filename || index + 1}`);
    img.loading = "lazy";
    img.decoding = "async";
    img.alt = "";
    img.src = image.preview_url || image.thumb_url || image.url;
    preview.className = "web-image-preview";
    preview.append(checkbox, img);
    title.textContent = image.filename || `Obraz ${index + 1}`;
    dimensions.textContent = webImageDimensions(image);
    size.textContent = formatFileSize(image.size_bytes || 0);
    format.textContent = image.mime_type || "format nieznany";
    source.textContent = isThumbnailWebImage(image) ? "miniatura" : image.source || "obraz";
    cache.textContent = webImageCacheLabel(image);
    meta.className = "web-image-meta";
    meta.append(title, dimensions, format, size, source);
    if (cache.textContent) {
      meta.append(cache);
    }
    card.className = `web-image-card ${checkbox.checked ? "selected" : ""}`;
    card.title = image.url;
    card.append(preview, meta);
    const setSelected = (selected) => {
      if (selected) {
        state.webImageSelected.add(index);
        queueWebImageCache(image, "web");
      } else {
        state.webImageSelected.delete(index);
      }
      checkbox.checked = selected;
      card.classList.toggle("selected", selected);
      renderWebImagesPicker();
    };
    checkbox.addEventListener("change", () => setSelected(checkbox.checked));
    card.addEventListener("click", (event) => {
      if (event.target === checkbox) return;
      setSelected(!state.webImageSelected.has(index));
    });
    webImagesOutput.appendChild(card);
  }
}

function webImagesErrorHelp(message) {
  const text = String(message || "");
  if (/cloudflare|challenge\s*403/i.test(text)) {
    return [
      "Strona pokazuje zabezpieczenie Cloudflare/challenge 403.",
      "Importer nie dostaje wtedy HTML-a produktu, tylko strone blokady, wiec nie ma z czego wyciagnac linkow do zdjec.",
      "To zwykle wymaga sesji prawdziwej przegladarki albo cookies z tej strony.",
    ];
  }
  if (/403|forbidden/i.test(text)) {
    return [
      "Serwer odrzucil pobieranie strony kodem 403 Forbidden.",
      "Najczesciej oznacza to blokade botow, brak wymaganej sesji albo ograniczenie hotlinkowania.",
    ];
  }
  if (/html/i.test(text)) {
    return [
      "Podany adres nie zwrocil strony HTML produktu.",
      "Importer potrzebuje strony z linkami do obrazow albo bezposrednich linkow do plikow graficznych.",
    ];
  }
  return ["Nie udalo sie pobrac listy zdjec z podanego adresu."];
}

function renderWebImagesError(error) {
  const message = error?.message || String(error || "Operacja nie powiodla sie.");
  state.webImages = [];
  state.webImageSelected.clear();
  state.webImageCache.clear();
  state.webImageCacheQueue = [];
  state.webImageCacheActive = 0;
  openWebImagesModal();
  if (webImagesStatus) {
    webImagesStatus.textContent = "Nie mozna pobrac zdjec";
  }
  if (!webImagesOutput) {
    return;
  }
  webImagesOutput.textContent = "";
  webImagesOutput.classList.add("empty-state");
  const wrapper = document.createElement("div");
  const title = document.createElement("strong");
  const details = document.createElement("span");
  wrapper.className = "web-image-error";
  title.textContent = message;
  details.textContent = webImagesErrorHelp(message).join(" ");
  wrapper.append(title, details);
  webImagesOutput.appendChild(wrapper);
}

async function scanWebImages() {
  const url = webImageUrl?.value?.trim() || "";
  if (!url) {
    formStatus.textContent = "Wklej link do strony ze zdjeciami.";
    return;
  }
  state.webImageScanMode = webImageScanMode?.value || "links";
  localStorage.setItem("picorg-web-image-scan-mode", state.webImageScanMode);
  scanWebImagesButton.disabled = true;
  scanWebImagesButton.textContent = "Pobieranie...";
  formStatus.textContent =
    state.webImageScanMode === "links"
      ? "Skanowanie linkow do zdjec..."
      : "Skanowanie strony i pobieranie metadanych zdjec...";
  try {
    const payload = await requestJson("/api/web-images/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        mode: state.webImageScanMode,
        filters: webImageFilters(),
      }),
      timeoutMs: 60000,
    });
    state.webImagePageUrl = payload.source_url || url;
    state.webImageScanMode = payload.mode || state.webImageScanMode;
    state.webImages = payload.images || [];
    state.webImageSelected.clear();
    state.webImageCache.clear();
    state.webImageCacheQueue = [];
    state.webImageCacheActive = 0;
    openWebImagesModal();
    renderWebImagesPicker();
    formStatus.textContent =
      state.webImageScanMode === "links"
        ? `Wykryto ${state.webImages.length} linkow do zdjec ze strony.`
        : `Wykryto ${state.webImages.length} zdjec spelniajacych warunki.`;
  } catch (error) {
    formStatus.textContent = error.message;
    renderWebImagesError(error);
  } finally {
    scanWebImagesButton.disabled = false;
    scanWebImagesButton.textContent = "Pobierz zdjecia";
  }
}

function freeSlotPrefixes(limit = Infinity) {
  const prefixes = [];
  for (const slot of state.slots || []) {
    if (isSlotFreeForNewFile(slot.prefix)) {
      prefixes.push(slot.prefix);
      if (prefixes.length >= limit) break;
    }
  }
  return prefixes;
}

function webImageCacheItem(prefix, image, payload) {
  return {
    id: ++state.slotUploadRequestId,
    prefix,
    file: null,
    name: payload.name || image.filename || "web-image.jpg",
    size: Number(payload.size_bytes || image.size_bytes || 0),
    type: image.mime_type || "image/jpeg",
    token: payload.token || "",
    url: payload.url || "",
    thumb_url: payload.thumb_url || "",
    file_version: payload.file_version || "",
    preprocessed: Boolean(payload.preprocessed),
    cache_timing: payload.timing || null,
    client_preprocess_ms: 0,
    progress: 100,
    uploading: false,
    error: "",
    xhr: null,
    provisional: false,
    placementBlocked: false,
  };
}

async function cacheWebImageForSlot(image, prefix) {
  return requestJson("/api/web-images/cache", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url: image.url,
      page_url: state.webImagePageUrl || webImageUrl?.value?.trim() || "",
      prefix,
    }),
    timeoutMs: 60000,
  });
}

async function addSelectedWebImagesToSlots() {
  const selected = [...state.webImageSelected]
    .sort((a, b) => a - b)
    .map((index) => state.webImages[index])
    .filter(Boolean);
  if (!selected.length) {
    formStatus.textContent = "Zaznacz zdjecia do dodania.";
    return;
  }
  const prefixes = freeSlotPrefixes(selected.length);
  if (!prefixes.length) {
    warnNoFreeSlots(selected.map((image) => image.filename || image.url));
    return;
  }
  webImagesAddButton.disabled = true;
  webImagesAddButton.textContent = "Dodawanie...";
  const assigned = [];
  try {
    const limit = Math.min(selected.length, prefixes.length);
    for (let index = 0; index < limit; index += 1) {
      const image = selected[index];
      const prefix = prefixes[index];
      formStatus.textContent = `Pobieranie zdjecia ${index + 1}/${limit} do slotu ${prefix}...`;
      const payload = await cachedWebImagePayload(image, prefix);
      if (!payload.token) {
        throw new Error("Backend nie zwrocil tokenu cache dla zdjecia.");
      }
      state.files.set(prefix, webImageCacheItem(prefix, image, payload));
      state.webImageSelected.delete(state.webImages.indexOf(image));
      assigned.push(prefix);
      renderSlot(prefix);
    }
    if (assigned.length) {
      formStatus.textContent = `Dodano ${assigned.length} zdjec do slotow: ${assigned.join(", ")}.`;
      updateSubmitButtonState();
    }
    if (selected.length > prefixes.length) {
      warnNoFreeSlots(selected.slice(prefixes.length).map((image) => image.filename || image.url));
    }
    renderWebImagesPicker();
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    webImagesAddButton.disabled = false;
    webImagesAddButton.textContent = "Dodaj do wolnych slotow";
  }
}

function imageFromBrowserExtensionItem(item) {
  const cache = item?.cache || {};
  return {
    url: item?.source_url || cache.url || "",
    preview_url: cache.thumb_url || cache.url || item?.source_url || "",
    thumb_url: cache.thumb_url || "",
    filename: item?.filename || cache.name || "web-image.jpg",
    width: Number(item?.width || cache.width || 0),
    height: Number(item?.height || cache.height || 0),
    size_bytes: Number(item?.size_bytes || cache.size_bytes || 0),
    mime_type: item?.mime_type || "image/jpeg",
    source: item?.source || "browser-extension",
    kind: item?.kind || "image",
    page_url: item?.page_url || "",
  };
}

function loadBrowserExtensionItems(items) {
  const imported = [];
  const existingByUrl = new Map(
    (state.webImages || []).map((image, index) => [webImageCacheKey(image), index])
  );
  for (const item of items || []) {
    const image = imageFromBrowserExtensionItem(item);
    if (!image.url) continue;
    const key = webImageCacheKey(image);
    if (!key) continue;
    state.webImageCache.set(key, {
      status: "ready",
      payload: item.cache || item,
      error: "",
      promise: null,
    });
    const existingIndex = existingByUrl.get(key);
    if (existingIndex !== undefined) {
      state.webImages[existingIndex] = {
        ...state.webImages[existingIndex],
        ...image,
      };
      state.webImageSelected.add(existingIndex);
      imported.push(image);
      continue;
    }
    const newIndex = state.webImages.length;
    state.webImages.push(image);
    state.webImageSelected.add(newIndex);
    existingByUrl.set(key, newIndex);
    imported.push(image);
  }
  if (!imported.length) {
    return 0;
  }
  state.webImagePageUrl = state.webImagePageUrl || imported[0]?.page_url || "";
  openWebImagesModal();
  renderWebImagesPicker();
  return imported.length;
}

async function receiveBrowserExtensionImages() {
  if (!browserExtensionReceiveButton) return;
  browserExtensionReceiveButton.disabled = true;
  browserExtensionReceiveButton.textContent = "Odbieranie...";
  try {
    const payload = await requestJson("/api/browser-extension/imports");
    const count = loadBrowserExtensionItems(payload.items || []);
    formStatus.textContent = count
      ? `Odebrano ${count} zdjec z rozszerzenia.`
      : "Brak nowych zdjec z rozszerzenia.";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    browserExtensionReceiveButton.disabled = false;
    browserExtensionReceiveButton.textContent = "Odbierz z rozszerzenia";
  }
}

async function downloadBrowserExtension() {
  if (!browserExtensionDownload) return;
  browserExtensionDownload.disabled = true;
  browserExtensionDownload.textContent = "Pobieranie...";
  try {
    const response = await fetch("/api/browser-extension/download", {
      cache: "no-store",
    });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok || !contentType.includes("application/zip")) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(
        payload.detail ||
          "Backend nie zwrocil paczki ZIP rozszerzenia. Sprawdz, czy EXE zawiera folder browser_extension."
      );
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "picorgftp-sql-browser-extension.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    formStatus.textContent = "Pobrano paczke rozszerzenia.";
  } catch (error) {
    formStatus.textContent = error.message;
  } finally {
    browserExtensionDownload.disabled = false;
    browserExtensionDownload.textContent = "Pobierz rozszerzenie";
  }
}

function currentProcessingSettings() {
  return state.settings?.processing || state.processing || {};
}

function currentSecuritySettings() {
  return state.settings?.security || state.security || {};
}

function extensionListText(value) {
  if (Array.isArray(value)) return value.join(", ");
  return String(value || "");
}

function normalizeUploadExtensionList(value) {
  const items = Array.isArray(value) ? value : String(value || "").split(/[\s,;]+/);
  return items
    .map((extension) => String(extension || "").trim().toLowerCase().replace(/^\.+/, ""))
    .filter((extension, index, list) => /^[a-z0-9]+$/.test(extension) && list.indexOf(extension) === index);
}

function uploadAcceptAttribute() {
  const security = currentSecuritySettings();
  const allowed = normalizeUploadExtensionList(security.allowed_upload_extensions);
  if (allowed.length) {
    const blocked = normalizeUploadExtensionList(security.blocked_upload_extensions);
    const pickerAllowed = allowed.filter(
      (extension) =>
        !blocked.includes(extension) &&
        !(security.block_executable_uploads !== false && CLIENT_EXECUTABLE_UPLOAD_EXTENSIONS.has(extension))
    );
    return pickerAllowed.length
      ? pickerAllowed.map((extension) => `.${extension}`).join(",")
      : ".picorg-no-allowed-upload";
  }
  return "image/*,.pdf,.eps,.psd,.ai,.tif,.tiff";
}

function uploadProcessingMode() {
  return currentProcessingSettings().upload_processing_mode || "save";
}

function timingPreferenceStorageKey() {
  const username = state.currentUser?.username || "anonymous";
  return `picorg-show-timing-${username}`;
}

function showTimingDetails() {
  const stored = localStorage.getItem(timingPreferenceStorageKey());
  if (stored === "1") return true;
  if (stored === "0") return false;
  return Boolean(currentProcessingSettings().show_timing_details);
}

function setTimingDetailsVisible(value) {
  localStorage.setItem(timingPreferenceStorageKey(), value ? "1" : "0");
  applyTimingDetailsVisibility();
}

function applyTimingDetailsVisibility() {
  if (resultSection) {
    resultSection.hidden = !showTimingDetails();
  }
}

function updateRuntimeMetrics() {
  if (fileIndexInfo) {
    fileIndexInfo.textContent = state.fileIndex?.label || "";
    fileIndexInfo.title = state.fileIndex?.error || "";
  }
  if (latencyInfo) {
    latencyInfo.textContent =
      state.lastLookupMs === null ? "" : `ostatnie wczytanie: ${Math.round(state.lastLookupMs)} ms`;
  }
}

function formValue(name) {
  return productForm.elements[name]?.value?.trim() || "";
}

function currentFormPayload() {
  return {
    name: formValue("name"),
    type_name: formValue("type_name"),
    model: formValue("model"),
    color1: formValue("color1"),
    color2: formValue("color2"),
    color3: formValue("color3"),
    extra: formValue("extra"),
  };
}

function uniqueValues(values, limit = Number.POSITIVE_INFINITY) {
  const seen = new Set();
  const result = [];
  const maxItems = Number.isFinite(limit) ? Math.max(1, Number(limit)) : Number.POSITIVE_INFINITY;
  for (const value of values || []) {
    const text = String(value || "").trim();
    if (!text) continue;
    const key = text.toUpperCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(text);
    if (result.length >= maxItems) break;
  }
  return result;
}

function setOptions(datalistId, values) {
  const datalist = document.querySelector(datalistId);
  datalist.textContent = "";
  for (const value of values || []) {
    const option = document.createElement("option");
    option.value = value;
    datalist.appendChild(option);
  }
}

function renderDatalists() {
  setOptions("#namesList", state.lists.names);
  setOptions("#typesList", state.lists.types);
  setOptions("#modelsList", state.lists.models);
  setOptions("#colorsList", state.lists.colors);
  setOptions("#extrasList", state.lists.extras);
}

const fieldListKey = {
  name: "names",
  type_name: "types",
  model: "models",
  color1: "colors",
  color2: "colors",
  color3: "colors",
  extra: "extras",
};

const fieldListLabels = {
  name: "Nazwa",
  type_name: "Typ",
  model: "Model",
  color1: "Kolor 1",
  color2: "Kolor 2",
  color3: "Kolor 3",
  extra: "Dodatek",
};

const productFieldDefinitions = {
  name: { input: "name", label: "Nazwa", required: true },
  type: { input: "type_name", label: "Typ", required: true },
  model: { input: "model", label: "Model", required: true },
  color1: { input: "color1", label: "Kolor 1", required: true },
  color2: { input: "color2", label: "Kolor 2", required: false },
  color3: { input: "color3", label: "Kolor 3", required: false },
  extra: { input: "extra", label: "Dodatek", required: false },
  ean: { input: "ean", label: "EAN", required: false },
};

function cleanDisplayLabel(value) {
  return String(value || "")
    .trim()
    .replace(/[:*]+$/g, "")
    .trim();
}

function productFieldLabel(fieldName) {
  const key =
    Object.entries(productFieldDefinitions).find(([_key, item]) => item.input === fieldName)?.[0] ||
    fieldName;
  const definition = productFieldDefinitions[key];
  if (!definition) return fieldListLabels[fieldName] || fieldName;
  return cleanDisplayLabel(state.productFields?.[key]?.label) || definition.label;
}

function normalizedProductFields(raw = {}) {
  return Object.fromEntries(
    Object.entries(productFieldDefinitions).map(([key, defaults]) => {
      const item = raw?.[key] || {};
      const enabled = item.enabled !== false;
      return [
        key,
        {
          label: cleanDisplayLabel(item.label),
          enabled,
          required: enabled && ("required" in item ? Boolean(item.required) : defaults.required),
        },
      ];
    })
  );
}

function applyProductFieldSettings() {
  state.productFields = normalizedProductFields(state.productFields);
  for (const [key, definition] of Object.entries(productFieldDefinitions)) {
    const item = state.productFields[key];
    const container = document.querySelector(`[data-product-field="${key}"]`);
    const label = document.querySelector(`[data-product-field-label="${key}"]`);
    const input = productForm.elements[definition.input];
    if (!container || !label || !input) continue;
    container.hidden = !item.enabled;
    input.disabled = !item.enabled;
    input.required = item.enabled && item.required;
    if (!item.enabled) input.value = "";
    label.textContent = `${item.label || definition.label}${item.required ? " *" : ""}`;
  }
  findByEanButton.hidden = !state.productFields.ean.enabled;
  updateFieldWarnings();
}

function applyProductFieldLabels() {
  applyProductFieldSettings();
}

function listHasValue(listKey, value) {
  const normalized = normalizeListValue(value);
  if (!normalized) return true;
  return (state.lists[listKey] || []).some((item) => normalizeListValue(item) === normalized);
}

function canonicalListValue(listKey, value) {
  const normalized = normalizeListValue(value);
  return (state.lists[listKey] || []).find((item) => normalizeListValue(item) === normalized) || "";
}

async function addValueToList(listKey, value) {
  const payload = await requestJson(`/api/lists/${listKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
  renderDatalists();
  renderListEditor();
  return canonicalListValue(listKey, value);
}

async function promptAddProductFieldToList(fieldName, { force = false } = {}) {
  const listKey = fieldListKey[fieldName];
  const input = productForm.elements[fieldName];
  const value = input?.value?.trim() || "";
  if (!listKey || !value || listHasValue(listKey, value)) {
    return false;
  }
  const promptKey = `${listKey}|${normalizeListValue(value)}`;
  if (state.activeListPromptKeys.has(promptKey)) {
    return false;
  }
  if (!force && state.declinedListPrompts.has(promptKey)) {
    return false;
  }
  state.activeListPromptKeys.add(promptKey);
  try {
    const label = productFieldLabel(fieldName);
    const listLabel = listLabels[listKey] || listKey;
    const shouldAdd = window.confirm(
      `${label}: "${value}" nie istnieje na liscie ${listLabel}. Dodac ten wpis do listy?`
    );
    if (!shouldAdd) {
      state.declinedListPrompts.add(promptKey);
      return false;
    }
    const canonical = await addValueToList(listKey, value);
    if (canonical) {
      input.value = canonical;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
    state.declinedListPrompts.delete(promptKey);
    formStatus.textContent = `Dodano "${canonical || value}" do listy ${listLabel}.`;
    return true;
  } finally {
    state.activeListPromptKeys.delete(promptKey);
  }
}

async function ensureProductListValues() {
  for (const fieldName of Object.keys(fieldListKey)) {
    await promptAddProductFieldToList(fieldName);
  }
}

function entryMatchesContext(entry, fieldName) {
  const payload = currentFormPayload();
  if (["type_name", "model", "color1", "color2", "color3", "extra"].includes(fieldName)) {
    if (payload.name && String(entry.name || "").toUpperCase() !== payload.name.toUpperCase()) return false;
  }
  if (["model", "color1", "color2", "color3", "extra"].includes(fieldName)) {
    if (payload.type_name && String(entry.type_name || "").toUpperCase() !== payload.type_name.toUpperCase()) return false;
  }
  if (["color1", "color2", "color3", "extra"].includes(fieldName)) {
    if (payload.model && String(entry.model || "").toUpperCase() !== payload.model.toUpperCase()) return false;
  }
  return true;
}

function localSuggestions(fieldName) {
  const existing = [];
  for (const entry of state.entries || []) {
    if (!entryMatchesContext(entry, fieldName)) continue;
    if (fieldName === "name") existing.push(entry.name);
    if (fieldName === "type_name") existing.push(entry.type_name);
    if (fieldName === "model") existing.push(entry.model);
    if (["color1", "color2", "color3"].includes(fieldName)) {
      existing.push(entry.color1, entry.color2, entry.color3);
    }
    if (fieldName === "extra") existing.push(entry.extra);
  }
  const listValues = state.lists[fieldListKey[fieldName]] || [];
  return uniqueValues([...existing, ...listValues]);
}

async function remoteSuggestions(fieldName) {
  const params = new URLSearchParams({ field: fieldName, ...currentFormPayload() });
  const payload = await requestJson(`/api/suggestions?${params.toString()}`);
  state.fileIndex = payload.file_index || state.fileIndex;
  updateRuntimeMetrics();
  return payload.values || [];
}

let activeAutocompletePanel = null;

function closeAutocompletePanels(exceptPanel = null) {
  activeAutocompletePanel = exceptPanel;
  document.querySelectorAll(".autocomplete-panel").forEach((panel) => {
    if (panel !== exceptPanel) panel.classList.remove("active");
  });
}

function autocompleteOptions(panel) {
  return [...panel.querySelectorAll('button[data-autocomplete-option="1"]')];
}

function setActiveAutocompleteOption(panel, index) {
  const options = autocompleteOptions(panel);
  if (!options.length) {
    panel.dataset.activeIndex = "-1";
    return;
  }
  const nextIndex = ((index % options.length) + options.length) % options.length;
  options.forEach((option, optionIndex) => {
    option.classList.toggle("active", optionIndex === nextIndex);
    option.setAttribute("aria-selected", optionIndex === nextIndex ? "true" : "false");
  });
  panel.dataset.activeIndex = String(nextIndex);
  options[nextIndex].scrollIntoView({ block: "nearest" });
}

function appendAutocompleteText(button, value, query) {
  const text = String(value || "");
  const needle = String(query || "").trim();
  if (!needle) {
    button.textContent = text;
    return;
  }
  const index = text.toLowerCase().indexOf(needle.toLowerCase());
  if (index < 0) {
    button.textContent = text;
    return;
  }
  button.append(
    document.createTextNode(text.slice(0, index)),
    Object.assign(document.createElement("mark"), { textContent: text.slice(index, index + needle.length) }),
    document.createTextNode(text.slice(index + needle.length))
  );
}

function commitAutocompleteValue(input, panel, value) {
  panel.dataset.selecting = "1";
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  closeAutocompletePanels();
  window.setTimeout(() => {
    panel.dataset.selecting = "";
  }, 0);
}

function renderAutocompletePanel(input, panel, values) {
  if (activeAutocompletePanel && activeAutocompletePanel !== panel && document.activeElement !== input) {
    return;
  }
  if (panel.dataset.selecting === "1") {
    return;
  }
  closeAutocompletePanels(panel);
  const previousScroll = panel.scrollTop;
  const typed = input.value.trim();
  const typedUpper = typed.toUpperCase();
  const filtered = values
    .filter((value) => !typedUpper || value.toUpperCase().includes(typedUpper))
    .slice(0, MAX_AUTOCOMPLETE_OPTIONS);
  panel.textContent = "";
  panel.dataset.activeIndex = "-1";
  if (!filtered.length) {
    panel.classList.remove("active");
    return;
  }
  for (const [index, value] of filtered.entries()) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.autocompleteOption = "1";
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", "false");
    appendAutocompleteText(button, value, typed);
    button.addEventListener("mouseenter", () => setActiveAutocompleteOption(panel, index));
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      commitAutocompleteValue(input, panel, value);
    });
    panel.appendChild(button);
  }
  panel.scrollTop = previousScroll;
  panel.classList.add("active");
  activeAutocompletePanel = panel;
}

function setupAutocomplete() {
  productForm.setAttribute("autocomplete", "off");
  for (const fieldName of Object.keys(fieldListKey)) {
    const input = productForm.elements[fieldName];
    if (!input) continue;
    input.removeAttribute("list");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("data-lpignore", "true");
    input.setAttribute("data-1p-ignore", "true");
    input.setAttribute("data-bwignore", "true");
    input.setAttribute("data-form-type", "other");
    input.setAttribute("readonly", "readonly");
    const host = input.closest("label");
    if (!host) continue;
    host.classList.add("autocomplete-host");
    const panel = document.createElement("div");
    panel.className = "autocomplete-panel";
    panel.setAttribute("role", "listbox");
    host.appendChild(panel);
    let requestId = 0;
    let remoteTimer = 0;
    const unlockBrowserAutofill = () => {
      input.removeAttribute("readonly");
      window.setTimeout(() => input.setAttribute("autocomplete", "off"), 0);
    };
    const refresh = () => {
      activeAutocompletePanel = panel;
      closeAutocompletePanels(panel);
      const local = localSuggestions(fieldName);
      renderAutocompletePanel(input, panel, local);
      const currentRequest = ++requestId;
      window.clearTimeout(remoteTimer);
      remoteTimer = window.setTimeout(() => {
        remoteSuggestions(fieldName)
          .then((values) => {
            if (currentRequest === requestId && activeAutocompletePanel === panel) {
              renderAutocompletePanel(input, panel, uniqueValues([...local, ...values]));
            }
          })
          .catch(() => {});
      }, 180);
    };
    input.addEventListener("mousedown", unlockBrowserAutofill);
    input.addEventListener("focus", unlockBrowserAutofill);
    input.addEventListener("focus", refresh);
    input.addEventListener("input", refresh);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAutocompletePanels();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Enter"].includes(event.key)) {
        return;
      }
      if (!panel.classList.contains("active")) {
        if (event.key === "Enter") {
          return;
        }
        refresh();
      }
      const options = autocompleteOptions(panel);
      if (!options.length) {
        return;
      }
      const currentIndex = Number(panel.dataset.activeIndex || "-1");
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveAutocompleteOption(panel, currentIndex + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveAutocompleteOption(panel, currentIndex - 1);
      } else if (event.key === "Enter" && currentIndex >= 0 && options[currentIndex]) {
        event.preventDefault();
        commitAutocompleteValue(input, panel, options[currentIndex].textContent || "");
      }
    });
  }
  document.addEventListener("mousedown", (event) => {
    if (!event.target.closest(".autocomplete-host")) closeAutocompletePanels();
  });
}

function renderEntrySelect(entries = state.entries) {
  entrySelect.textContent = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = entries.length ? "Wybierz wpis" : "Brak dopasowan";
  entrySelect.appendChild(empty);
  for (const entry of entries) {
    const option = document.createElement("option");
    option.value = entry.product_id || entry.ean;
    option.textContent = entry.label;
    option.dataset.entry = JSON.stringify(entry);
    entrySelect.appendChild(option);
  }
}

function renderEntryModal(entries) {
  entryMatches.textContent = "";
  if (!entries.length) {
    entryMatches.textContent = "Brak dopasowanych wpisow.";
    document.querySelector("#entryModal").classList.add("active");
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("article");
    row.className = "entry-match";
    const text = document.createElement("div");
    const title = document.createElement("strong");
    const details = document.createElement("span");
    const button = document.createElement("button");
    title.textContent = entry.label;
    details.textContent = `${entry.product_id || "BRAK-ID"} | ${entry.ean || "BRAK-EAN"}`;
    button.type = "button";
    button.textContent = "Wczytaj";
    button.addEventListener("click", () => {
      fillForm(entry, { loadPhotos: true });
      closeModals();
    });
    text.append(title, details);
    row.append(text, button);
    entryMatches.appendChild(row);
  }
  document.querySelector("#entryModal").classList.add("active");
}

function renderListUsageModal(value, usedBy = []) {
  if (!listUsageTitle || !listUsageOutput) {
    return;
  }
  listUsageTitle.textContent = `Nie usunieto: ${value}`;
  listUsageOutput.textContent = "";
  if (!usedBy.length) {
    listUsageOutput.textContent = "Backend nie zwrocil listy produktow.";
    document.querySelector("#listUsageModal")?.classList.add("active");
    return;
  }
  for (const item of usedBy) {
    const row = document.createElement("article");
    const text = document.createElement("div");
    const title = document.createElement("strong");
    const details = document.createElement("span");
    row.className = "entry-match";
    title.textContent = item.label || `${item.name || ""} ${item.type_name || ""} ${item.model || ""}`.trim();
    details.textContent = `${item.product_id || "BRAK-ID"} | EAN ${item.ean || "BRAK-EAN"} | ${
      item.fields || "pole"
    }`;
    text.append(title, details);
    row.appendChild(text);
    listUsageOutput.appendChild(row);
  }
  document.querySelector("#listUsageModal")?.classList.add("active");
}

const trackedProductFields = [
  "name",
  "type_name",
  "model",
  "color1",
  "color2",
  "color3",
  "extra",
  "ean",
];

function updateFieldWarnings() {
  for (const fieldName of trackedProductFields) {
    const input = productForm.elements[fieldName];
    if (!input) continue;
    const label = input.closest("label");
    if (!label) continue;
    let warning = label.querySelector(".field-warning");
    if (!warning) {
      warning = document.createElement("span");
      warning.className = "field-warning";
      label.appendChild(warning);
    }
    const original = state.loadedEntryOriginal ? String(state.loadedEntryOriginal[fieldName] || "") : "";
    const current = String(input.value || "");
    const changed = Boolean(state.loadedEntryOriginal) && current !== original;
    label.classList.toggle("field-changed", changed);
    warning.textContent = "";
    warning.classList.toggle("active", changed);
    if (changed) {
      const text = document.createElement("span");
      const undo = document.createElement("button");
      text.textContent = `Bylo: ${original || "(puste)"}`;
      undo.type = "button";
      undo.textContent = "Cofnij";
      undo.addEventListener("click", () => {
        input.value = original;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        updateFieldWarnings();
      });
      warning.append(text, undo);
    }
  }
  updateSubmitButtonState();
}

function setupFieldChangeTracking() {
  for (const fieldName of trackedProductFields) {
    productForm.elements[fieldName]?.addEventListener("input", updateFieldWarnings);
  }
}

function defaultSlotSource(photo) {
  if (photo?.local && photo?.token) return "local";
  if (photo?.ftp && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  return "";
}

function selectedSlotSource(prefix, photo) {
  const selected = state.slotSources.get(prefix);
  if (selected === "local" && photo?.token) return "local";
  if (selected === "ftp" && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  return defaultSlotSource(photo);
}

function selectedPhotoToken(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  if (source === "ftp") return photo?.ftp_token || "";
  return photo?.token || "";
}

function transferableSlotSource(prefix, photo) {
  const selected = state.slotSources.get(prefix);
  if (selected === "local" && photo?.token) return "local";
  if (selected === "ftp" && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  if (photo?.token) return "local";
  if (photo?.ftp_token || photo?.ftp_filename) return "ftp";
  return "";
}

function transferablePhotoToken(photo, prefix) {
  const source = transferableSlotSource(prefix, photo);
  if (source === "ftp") return photo?.ftp_token || "";
  if (source === "local") return photo?.token || "";
  return "";
}

function revokeFilePreviewUrl(prefix) {
  const url = state.filePreviewUrls.get(prefix);
  if (url) URL.revokeObjectURL(url);
  state.filePreviewUrls.delete(prefix);
}

function filePreviewUrl(prefix, file) {
  const item = slotFileItem(file);
  const rawFile = slotFileObject(item);
  if (!rawFile) {
    return item?.url || item?.thumb_url || "";
  }
  const current = state.filePreviewUrls.get(prefix);
  if (current) return current;
  const url = URL.createObjectURL(rawFile);
  state.filePreviewUrls.set(prefix, url);
  return url;
}

function isFileImageLike(file) {
  const name = String(slotFileName(file) || "").toLowerCase();
  return (
    String(slotFileType(file) || "").startsWith("image/") ||
    [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".psd", ".eps", ".ai"].some((ext) =>
      name.endsWith(ext)
    )
  );
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

function fittedImageDataUrl(image) {
  const sourceWidth = image.naturalWidth || image.width;
  const sourceHeight = image.naturalHeight || image.height;
  if (!sourceWidth || !sourceHeight) return "";
  const detectScale = Math.min(1, 512 / Math.max(sourceWidth, sourceHeight));
  const detectWidth = Math.max(1, Math.round(sourceWidth * detectScale));
  const detectHeight = Math.max(1, Math.round(sourceHeight * detectScale));
  const detect = document.createElement("canvas");
  detect.width = detectWidth;
  detect.height = detectHeight;
  const detectCtx = detect.getContext("2d", { willReadFrequently: true });
  detectCtx.drawImage(image, 0, 0, detectWidth, detectHeight);
  const pixels = detectCtx.getImageData(0, 0, detectWidth, detectHeight).data;
  const cornerSize = Math.max(1, Math.min(detectWidth, detectHeight, Math.floor(Math.min(detectWidth, detectHeight) / 20) || 1));
  const corners = [
    [0, 0],
    [detectWidth - cornerSize, 0],
    [0, detectHeight - cornerSize],
    [detectWidth - cornerSize, detectHeight - cornerSize],
  ];
  const bg = [0, 0, 0, 0];
  let bgCount = 0;
  for (const [startX, startY] of corners) {
    for (let y = startY; y < startY + cornerSize; y += 1) {
      for (let x = startX; x < startX + cornerSize; x += 1) {
        const idx = (y * detectWidth + x) * 4;
        bg[0] += pixels[idx];
        bg[1] += pixels[idx + 1];
        bg[2] += pixels[idx + 2];
        bg[3] += pixels[idx + 3];
        bgCount += 1;
      }
    }
  }
  bg[0] = bg[0] / Math.max(1, bgCount);
  bg[1] = bg[1] / Math.max(1, bgCount);
  bg[2] = bg[2] / Math.max(1, bgCount);
  bg[3] = bg[3] / Math.max(1, bgCount);
  let left = detectWidth;
  let top = detectHeight;
  let right = -1;
  let bottom = -1;
  for (let y = 0; y < detectHeight; y += 1) {
    for (let x = 0; x < detectWidth; x += 1) {
      const idx = (y * detectWidth + x) * 4;
      const alpha = pixels[idx + 3];
      const diff =
        Math.abs(pixels[idx] - bg[0]) +
        Math.abs(pixels[idx + 1] - bg[1]) +
        Math.abs(pixels[idx + 2] - bg[2]);
      const alphaDiff = Math.abs(alpha - bg[3]);
      if ((bg[3] < 250 && alpha > 8) || alphaDiff > 32 || (alpha > 8 && diff > 54)) {
        left = Math.min(left, x);
        top = Math.min(top, y);
        right = Math.max(right, x + 1);
        bottom = Math.max(bottom, y + 1);
      }
    }
  }
  if (right <= left || bottom <= top) return "";
  const areaRatio = ((right - left) * (bottom - top)) / Math.max(1, detectWidth * detectHeight);
  if (areaRatio > 0.98) return "";
  const scaleX = sourceWidth / detectWidth;
  const scaleY = sourceHeight / detectHeight;
  let cropLeft = Math.floor(left * scaleX);
  let cropTop = Math.floor(top * scaleY);
  let cropRight = Math.ceil(right * scaleX);
  let cropBottom = Math.ceil(bottom * scaleY);
  const margin = Math.ceil(Math.max(cropRight - cropLeft, cropBottom - cropTop) * 0.06);
  cropLeft = Math.max(0, cropLeft - margin);
  cropTop = Math.max(0, cropTop - margin);
  cropRight = Math.min(sourceWidth, cropRight + margin);
  cropBottom = Math.min(sourceHeight, cropBottom + margin);
  const sourceAspect = sourceWidth / Math.max(1, sourceHeight);
  let cropWidth = cropRight - cropLeft;
  let cropHeight = cropBottom - cropTop;
  if (cropWidth / cropHeight < sourceAspect) {
    const targetWidth = Math.min(sourceWidth, cropHeight * sourceAspect);
    cropLeft = Math.max(0, Math.min(sourceWidth - targetWidth, cropLeft - (targetWidth - cropWidth) / 2));
    cropWidth = targetWidth;
  } else {
    const targetHeight = Math.min(sourceHeight, cropWidth / sourceAspect);
    cropTop = Math.max(0, Math.min(sourceHeight - targetHeight, cropTop - (targetHeight - cropHeight) / 2));
    cropHeight = targetHeight;
  }
  const outScale = Math.min(1, 1200 / Math.max(sourceWidth, sourceHeight));
  const outWidth = Math.max(1, Math.round(sourceWidth * outScale));
  const outHeight = Math.max(1, Math.round(sourceHeight * outScale));
  const out = document.createElement("canvas");
  out.width = outWidth;
  out.height = outHeight;
  out
    .getContext("2d")
    .drawImage(image, cropLeft, cropTop, cropWidth, cropHeight, 0, 0, outWidth, outHeight);
  return out.toDataURL("image/jpeg", 0.9);
}

async function renderSelectedFilePreview(prefix, file, preview, previewImage, empty) {
  const url = filePreviewUrl(prefix, file);
  if (!url) {
    preview.classList.remove("thumb-loading", "has-image");
    empty.textContent = slotFileName(file);
    return;
  }
  preview.classList.add("thumb-loading");
  try {
    const image = await loadImage(url);
    if (state.files.get(prefix) !== file || !document.body.contains(preview)) return;
    const fitted = isSlotFit(prefix) ? fittedImageDataUrl(image) : "";
    previewImage.src = fitted || url;
    preview.classList.add("has-image");
    preview.classList.remove("thumb-loading");
  } catch (_error) {
    if (state.files.get(prefix) !== file || !document.body.contains(preview)) return;
    preview.classList.remove("thumb-loading", "has-image");
    empty.textContent = "Podglad niedostepny";
  }
}

function loadedFileUrl(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  if (source === "ftp" && photo?.ftp_url) return photo.ftp_url;
  if (source === "local" && photo?.url) return photo.url;
  const token = selectedPhotoToken(photo, prefix);
  return token ? `/api/file?token=${encodeURIComponent(token)}` : "";
}

async function openSlotFile(prefix) {
  const selectedFile = state.files.get(prefix);
  if (selectedFile) {
    window.open(filePreviewUrl(prefix, selectedFile), "_blank", "noopener");
    return;
  }
  let photo = state.loadedPhotos.get(prefix);
  if (selectedSlotSource(prefix, photo) === "ftp" && photo?.ftp_filename && !photo.ftp_token) {
    await loadFtpPreview(photo, prefix);
    photo = state.loadedPhotos.get(prefix);
  }
  const url = loadedFileUrl(photo, prefix);
  if (url) window.open(url, "_blank", "noopener");
}

function markSlotDeletion(prefix, photo) {
  if (!photo) return;
  state.deletedSlots.set(prefix, {
    prefix,
    token: photo.token || "",
    ftp_filename: photo.ftp_filename || "",
    sql: Boolean(photo.sql),
    filename: photo.filename || "",
    source: selectedSlotSource(prefix, photo),
  });
}

function slotStatusText(photo, prefix = "") {
  if (!photo) {
    return "Przeciagnij albo wybierz plik";
  }
  if (selectedSlotSource(prefix, photo) === "ftp" && photo.ftp_filename) {
    return `FTP: ${photo.ftp_filename}`;
  }
  if (photo.filename) {
    return photo.filename;
  }
  if (photo.ftp_filename) {
    return `FTP: ${photo.ftp_filename}`;
  }
  const parts = [];
  if (photo.local) parts.push("LOCAL");
  if (photo.ftp) parts.push("FTP");
  if (photo.sql) parts.push("SQL");
  return parts.length ? parts.join(" / ") : "Brak lokalnego pliku";
}

async function copyTextToClipboard(text, successMessage = "Skopiowano.") {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      formStatus.textContent = successMessage;
      return;
    } catch (_error) {
      // Older LAN/browser contexts can expose clipboard but still reject writes.
    }
  }
  const field = document.createElement("textarea");
  field.value = text;
  field.style.position = "fixed";
  field.style.left = "-9999px";
  document.body.appendChild(field);
  field.focus();
  field.select();
  document.execCommand("copy");
  field.remove();
  formStatus.textContent = successMessage;
}

function renderSlotBadges(container, photo, file, prefix) {
  const badges = document.createElement("div");
  badges.className = "slot-badges";
  const statuses = [
    ["local", "LOCAL", "Plik jest w folderze backendu"],
    ["ftp", "FTP", "Wpis dla slotu jest na FTP"],
    ["sql", "SQL", "Wpis dla slotu jest w SQL"],
  ];
  if (file) {
    const badge = document.createElement("span");
    badge.className = "slot-badge on";
    badge.title = "Nowy plik wybrany w przegladarce";
    badge.textContent = "NOWY";
    badges.appendChild(badge);
  }
  for (const [key, label, title] of statuses) {
    const sqlValue = String(photo?.sql_value || "").trim();
    const canPreview =
      (key === "local" && photo?.token) ||
      (key === "ftp" && photo?.ftp_filename);
    const canCopySql = key === "sql" && Boolean(sqlValue);
    const badge = document.createElement(canPreview || canCopySql ? "button" : "span");
    const selected = key !== "sql" && selectedSlotSource(prefix, photo) === key;
    const loading =
      isPhotoSourceLoading(key) || (key === "ftp" && state.ftpPreviewLoading.has(prefix));
    badge.dataset.source = key;
    badge.className = `slot-badge slot-badge-${key} ${photo && photo[key] ? "on" : ""} ${
      selected ? "selected" : ""
    } ${loading ? "loading" : ""}`;
    badge.title = loading
      ? sourceLoadingTitle(key)
      : canCopySql
      ? "Kliknij, aby skopiowac link z SQL"
      : selected
      ? `${title} (aktywny podglad)`
      : title;
    badge.textContent = label;
    if (canPreview || canCopySql) {
      badge.type = "button";
      badge.setAttribute("aria-pressed", selected ? "true" : "false");
      if (loading) {
        badge.setAttribute("aria-busy", "true");
      }
      badge.addEventListener("click", (event) => {
        event.stopPropagation();
        if (canCopySql) {
          copyTextToClipboard(sqlValue, `Skopiowano link SQL dla slotu ${prefix}.`).catch((error) => {
            formStatus.textContent = error.message;
          });
          return;
        }
        state.slotSources.set(prefix, key);
        state.userSelectedSlotSources.add(prefix);
        if (key === "ftp" && !photo.ftp_token) {
          if (state.ftpPreviewLoading.has(prefix)) {
            state.ftpPreviewBackgroundLoading.delete(prefix);
            updateSlotPreview(prefix);
          } else {
            loadFtpPreview(photo, prefix).catch((error) => {
              formStatus.textContent = error.message;
            });
          }
        } else {
          updateSlotPreview(prefix);
        }
      });
    }
    badges.appendChild(badge);
  }
  container.appendChild(badges);
}

function isPhotoSourceLoading(source) {
  const status = state.photoSourceStatus.get(source);
  return status === "pending" || status === "loading";
}

function sourceLoadingTitle(source) {
  if (source === "ftp") {
    return "Wczytywanie FTP";
  }
  if (source === "local") {
    return "Wczytywanie plikow lokalnych";
  }
  if (source === "sql") {
    return "Wczytywanie SQL";
  }
  return "Wczytywanie danych";
}

function photoHasUsableContent(photo) {
  if (!photo) return false;
  return Boolean(
    photo.token ||
      photo.url ||
      photo.thumb_url ||
      photo.filename ||
      photo.ftp_token ||
      photo.ftp_filename ||
      photo.ftp_url ||
      photo.ftp_thumb_url ||
      photo.sql_value ||
      photo.local ||
      photo.ftp ||
      photo.sql
  );
}

function isProvisionalSlotPlacement(prefix) {
  return Boolean(state.photosLoading && !photoHasUsableContent(state.loadedPhotos.get(prefix)));
}

function createSlotFileUpload(prefix, file, options = {}) {
  return {
    id: ++state.slotUploadRequestId,
    prefix,
    file,
    name: file?.name || "",
    size: Number(file?.size || 0),
    type: file?.type || "",
    token: "",
    url: "",
    thumb_url: "",
    file_version: "",
    preprocessed: false,
    cache_timing: null,
    client_preprocess_ms: 0,
    progress: 0,
    uploading: false,
    error: "",
    xhr: null,
    provisional: Boolean(options.provisional),
    placementBlocked: false,
  };
}

function uploadCacheErrorMessage(payload, fallback = "Nie udalo sie wyslac pliku do cache.") {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail?.message) return detail.message;
  return fallback;
}

function fileItemPrefixes(item) {
  const prefixes = [];
  for (const [prefix, current] of state.files.entries()) {
    if (current === item) prefixes.push(prefix);
  }
  return prefixes;
}

function refreshFileItemSlots(item) {
  for (const prefix of fileItemPrefixes(item)) {
    updateSlotPreview(prefix);
  }
  updateSubmitButtonState();
}

function clientTargetFormatInfo(file) {
  const settings = currentProcessingSettings();
  const sourceType = String(file?.type || "").toLowerCase();
  const sourceName = String(file?.name || "");
  const sourceExt = sourceName.split(".").pop()?.toLowerCase() || "";
  if (settings.convert_enabled) {
    const target = String(settings.target_format || "PNG").toUpperCase();
    if (target === "JPG" || target === "JPEG") return { type: "image/jpeg", ext: "jpg" };
    if (target === "PNG") return { type: "image/png", ext: "png" };
    if (target === "WEBP") return { type: "image/webp", ext: "webp" };
  }
  if (sourceType === "image/jpeg" || sourceExt === "jpg" || sourceExt === "jpeg") {
    return { type: "image/jpeg", ext: "jpg" };
  }
  if (sourceType === "image/png" || sourceExt === "png") return { type: "image/png", ext: "png" };
  if (sourceType === "image/webp" || sourceExt === "webp") return { type: "image/webp", ext: "webp" };
  return null;
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Przegladarka nie utworzyla przetworzonego obrazu."));
        }
      },
      type,
      quality
    );
  });
}

function loadImageForProcessing(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Nie udalo sie odczytac obrazu po stronie klienta."));
    };
    image.src = url;
  });
}

async function preprocessFileOnClient(file) {
  const settings = currentProcessingSettings();
  if (uploadProcessingMode() !== "client") {
    return { file, preprocessed: false, elapsed_ms: 0 };
  }
  if (
    !settings.resize_enabled &&
    !settings.compress_enabled &&
    !settings.max_size_enabled &&
    !settings.convert_enabled
  ) {
    return { file, preprocessed: false, elapsed_ms: 0 };
  }
  const format = clientTargetFormatInfo(file);
  if (!format) {
    return { file, preprocessed: false, elapsed_ms: 0 };
  }
  const started = performance.now();
  const image = await loadImageForProcessing(file);
  const maxDim = Math.max(64, Math.min(20000, Number(settings.max_dim || 2000)));
  let width = image.naturalWidth || image.width;
  let height = image.naturalHeight || image.height;
  if (settings.resize_enabled && Math.max(width, height) > maxDim) {
    const scale = maxDim / Math.max(width, height);
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { alpha: format.type !== "image/jpeg" });
  if (!ctx) {
    return { file, preprocessed: false, elapsed_ms: performance.now() - started };
  }
  if (format.type === "image/jpeg") {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
  }
  ctx.drawImage(image, 0, 0, width, height);
  const qualityBase = Math.max(1, Math.min(100, Number(settings.compress_quality || 85))) / 100;
  let quality = settings.compress_enabled ? qualityBase : 0.95;
  let blob = await canvasToBlob(canvas, format.type, quality);
  if (settings.max_size_enabled && ["image/jpeg", "image/webp"].includes(format.type)) {
    const maxBytes = Math.max(1, Number(settings.max_file_kb || 500)) * 1024;
    while (blob.size > maxBytes && quality > 0.1) {
      quality = Math.max(0.1, quality - 0.05);
      blob = await canvasToBlob(canvas, format.type, quality);
    }
  }
  const sourceName = String(file.name || "upload");
  const stem = sourceName.includes(".") ? sourceName.replace(/\.[^.]+$/, "") : sourceName;
  const processed = new File([blob], `${stem}.${format.ext}`, {
    type: format.type,
    lastModified: Date.now(),
  });
  return {
    file: processed,
    preprocessed: true,
    elapsed_ms: performance.now() - started,
    original_size: file.size || 0,
  };
}

function uploadSlotFile(prefix, item) {
  const file = slotFileObject(item);
  if (!file) return;
  const requestId = item.id;
  item.uploading = true;
  item.progress = 0;
  item.error = "";
  item.token = "";
  item.url = "";
  item.thumb_url = "";
  item.file_version = "";
  item.preprocessed = false;
  item.client_preprocess_ms = 0;
  item.original_size = Number(file.size || item.size || 0);
  refreshFileItemSlots(item);
  const sendUpload = (uploadFile, clientPreprocessed = false) => {
    if (item.id !== requestId) return;
    const data = new FormData();
    data.set("prefix", prefix);
    data.set("file", uploadFile, uploadFile.name || slotFileName(item));
  const xhr = new XMLHttpRequest();
  item.xhr = xhr;
  xhr.upload.addEventListener("progress", (event) => {
    if (!event.lengthComputable) return;
    const nextProgress = Math.max(1, Math.min(99, Math.round((event.loaded / event.total) * 100)));
    if (nextProgress === item.progress) return;
    item.progress = nextProgress;
    formStatus.textContent = `Wysylanie pliku dla slotu ${prefix}: ${nextProgress}%`;
    refreshFileItemSlots(item);
  });
  xhr.addEventListener("load", () => {
    const payload = xhr.response || {};
    if (xhr.status === 401) {
      window.location.href = "/login";
      return;
    }
    if (xhr.status < 200 || xhr.status >= 300) {
      item.uploading = false;
      item.error = uploadCacheErrorMessage(payload);
      item.xhr = null;
      formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
      refreshFileItemSlots(item);
      return;
    }
    if (!payload.token) {
      item.uploading = false;
      item.error = "Backend nie zwrocil tokenu cache.";
      item.xhr = null;
      formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
      refreshFileItemSlots(item);
      return;
    }
    item.token = payload.token || "";
    item.url = payload.url || "";
    item.thumb_url = payload.thumb_url || "";
    item.file_version = payload.file_version || "";
    item.preprocessed = Boolean(payload.preprocessed || clientPreprocessed);
    item.client_preprocess_ms = item.client_preprocess_ms || 0;
    item.cache_timing = payload.timing || null;
    item.name = payload.name || item.name;
    item.size = Number(payload.size_bytes || item.size || 0);
    item.progress = 100;
    item.uploading = false;
    item.error = "";
    item.xhr = null;
    const timingText =
      showTimingDetails() && payload.timing?.total_ms
        ? ` (${formatDuration(payload.timing.total_ms)})`
        : "";
    formStatus.textContent = `Plik dla slotu ${prefix} jest w cache${timingText}.`;
    refreshFileItemSlots(item);
  });
  xhr.addEventListener("error", () => {
    item.uploading = false;
    item.error = "Nie udalo sie polaczyc z backendem podczas uploadu.";
    item.xhr = null;
    formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
    refreshFileItemSlots(item);
  });
  xhr.addEventListener("abort", () => {
    item.uploading = false;
    item.error = "Upload przerwany.";
    item.xhr = null;
    refreshFileItemSlots(item);
  });
  xhr.open("POST", "/api/upload-cache");
  xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
  if (state.csrfToken) {
    xhr.setRequestHeader(CSRF_HEADER, state.csrfToken);
  }
  xhr.responseType = "json";
  xhr.send(data);
  };
  preprocessFileOnClient(file)
    .then((prepared) => {
      if (item.id !== requestId) return;
      item.client_preprocess_ms = Math.round(prepared.elapsed_ms || 0);
      if (prepared.preprocessed) {
        item.file = prepared.file;
        item.name = prepared.file.name || item.name;
        item.size = Number(prepared.file.size || item.size || 0);
      }
      sendUpload(prepared.file, prepared.preprocessed);
    })
    .catch((error) => {
      item.uploading = false;
      item.error = error.message || "Nie udalo sie przygotowac obrazu po stronie klienta.";
      item.xhr = null;
      formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
      refreshFileItemSlots(item);
    });
  updateSubmitButtonState();
}

function activeSlotUploads() {
  return [...state.files.entries()].filter(([, item]) => isSlotUploadActive(item));
}

function failedSlotUploads() {
  return [...state.files.entries()].filter(([, item]) => Boolean(slotUploadError(item)));
}

function ensureSlotUploadsReady() {
  const pending = activeSlotUploads();
  if (pending.length) {
    throw new Error("Poczekaj na zakonczenie wysylania plikow do cache.");
  }
  const failed = failedSlotUploads();
  if (failed.length) {
    const [prefix, item] = failed[0];
    throw new Error(`Upload slotu ${prefix} nie powiodl sie: ${slotUploadError(item)}`);
  }
}

function renderSlotUploadOverlay(preview, item) {
  preview.querySelector(".slot-upload-overlay")?.remove();
  const error = slotUploadError(item);
  if (!isSlotUploadActive(item) && !error) return;
  const overlay = document.createElement("div");
  const label = document.createElement("span");
  const line = document.createElement("div");
  const bar = document.createElement("i");
  const progress = slotUploadProgress(item);
  overlay.className = `slot-upload-overlay ${error ? "error" : ""}`;
  label.textContent = error ? `Upload nieudany: ${error}` : `Wysylanie ${progress}%`;
  line.className = "progress-line upload-progress-line";
  line.style.setProperty("--upload-progress", `${progress}%`);
  line.appendChild(bar);
  overlay.append(label, line);
  preview.appendChild(overlay);
}

function setFtpBadgeLoading(prefix, loading) {
  const card = slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`);
  const badge = card?.querySelector('.slot-badge-ftp[data-source="ftp"]');
  if (!badge) return;
  const selected = badge.classList.contains("selected");
  badge.classList.toggle("loading", Boolean(loading));
  if (loading) {
    badge.setAttribute("aria-busy", "true");
    badge.title = "Pobieranie miniatury FTP w tle";
  } else {
    badge.removeAttribute("aria-busy");
    badge.title = selected ? "Wpis dla slotu jest na FTP (aktywny podglad)" : "Wpis dla slotu jest na FTP";
  }
}

function slotRevision(prefix) {
  return Number(state.slotRevisions.get(prefix) || 0);
}

function bumpSlotRevision(prefix) {
  state.slotRevisions.set(prefix, slotRevision(prefix) + 1);
}

function ftpPreviewCacheKey(photo, fallbackEan = "") {
  const filename = String(photo?.ftp_filename || "").trim();
  const ean = String(photo?.ean || fallbackEan || "").trim();
  return filename && ean ? `${ean}|${filename}` : "";
}

function clearFtpPreviewCacheForPrefixes(prefixes, fallbackEan = "") {
  const prefixSet = new Set(
    [...(prefixes || [])].map((prefix) => String(prefix || "").trim()).filter(Boolean)
  );
  if (!prefixSet.size) return;
  const ean = String(fallbackEan || formValue("ean") || state.loadedEntryOriginal?.ean || "").trim();
  for (const prefix of prefixSet) {
    const photo = state.loadedPhotos.get(prefix);
    const directKey = ftpPreviewCacheKey(photo, ean);
    if (directKey) {
      state.ftpPreviewCache.delete(directKey);
    }
  }
  for (const key of Array.from(state.ftpPreviewCache.keys())) {
    const [keyEan, filename] = String(key).split("|", 2);
    if (ean && keyEan && keyEan !== ean) continue;
    for (const prefix of prefixSet) {
      if (filename?.startsWith(`${keyEan}_${prefix}.`) || filename?.includes(`_${prefix}.`)) {
        state.ftpPreviewCache.delete(key);
        break;
      }
    }
  }
}

function applyCachedFtpPreview(photo, prefix, cached) {
  if (!cached) return photo;
  if (cached.file_version && photo?.ftp_file_version && cached.file_version !== photo.ftp_file_version) {
    return photo;
  }
  return {
    ...photo,
    ftp_token: cached.token || photo?.ftp_token || "",
    ftp_url: cached.url || photo?.ftp_url || "",
    ftp_thumb_url: cached.thumb_url || photo?.ftp_thumb_url || "",
    ftp_file_version: cached.file_version || photo?.ftp_file_version || "",
  };
}

async function loadFtpPreview(photo, prefix, requestId = state.photoLoadRequestId, options = {}) {
  if (!photo?.ftp_filename || state.ftpPreviewLoading.has(prefix)) return;
  const revision = slotRevision(prefix);
  const cacheKey = ftpPreviewCacheKey(photo, formValue("ean") || "");
  const sourceBefore = selectedSlotSource(prefix, photo);
  const explicitSourceBefore = state.slotSources.get(prefix);
  const cached = cacheKey ? state.ftpPreviewCache.get(cacheKey) : null;
  if (cached) {
    const currentPhoto = state.loadedPhotos.get(prefix);
    if (
      requestId !== state.photoLoadRequestId ||
      revision !== slotRevision(prefix) ||
      !currentPhoto ||
      ftpPreviewCacheKey(currentPhoto, formValue("ean") || "") !== cacheKey
    ) {
      return;
    }
    const updated = applyCachedFtpPreview(currentPhoto, prefix, cached);
    state.loadedPhotos.set(prefix, updated);
    if (!options.background || sourceBefore === "ftp") {
      state.slotSources.set(prefix, "ftp");
    } else if (explicitSourceBefore) {
      state.slotSources.set(prefix, explicitSourceBefore);
    }
    if (options.background && selectedSlotSource(prefix, updated) !== "ftp") {
      setFtpBadgeLoading(prefix, false);
    } else {
      updateSlotPreview(prefix);
    }
    return;
  }
  state.ftpPreviewLoading.add(prefix);
  const background = Boolean(options.background);
  if (background) {
    state.ftpPreviewBackgroundLoading.add(prefix);
  } else {
    state.ftpPreviewBackgroundLoading.delete(prefix);
  }
  if (!background) {
    formStatus.textContent = `Pobieranie podgladu FTP dla slotu ${prefix}...`;
  }
  if (background) {
    setFtpBadgeLoading(prefix, true);
  } else {
    updateSlotPreview(prefix);
  }
  try {
    const payload = await requestJson("/api/ftp-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ean: photo.ean || formValue("ean") || "", filename: photo.ftp_filename }),
    });
    if (cacheKey) {
      state.ftpPreviewCache.set(cacheKey, {
        token: payload.token || "",
        url: payload.url || "",
        thumb_url: payload.thumb_url || "",
        file_version: payload.file_version || "",
      });
    }
    const currentPhoto = state.loadedPhotos.get(prefix);
    if (
      requestId !== state.photoLoadRequestId ||
      revision !== slotRevision(prefix) ||
      !currentPhoto ||
      ftpPreviewCacheKey(currentPhoto, formValue("ean") || "") !== cacheKey
    ) {
      return;
    }
    const updated = {
      ...currentPhoto,
      ftp_token: payload.token || "",
      ftp_url: payload.url || "",
      ftp_thumb_url: payload.thumb_url || "",
      ftp_file_version: payload.file_version || "",
    };
    state.loadedPhotos.set(prefix, updated);
    if (!background || sourceBefore === "ftp") {
      state.slotSources.set(prefix, "ftp");
    } else if (explicitSourceBefore) {
      state.slotSources.set(prefix, explicitSourceBefore);
    }
    if (!background) {
      formStatus.textContent = `Pobrano podglad FTP dla slotu ${prefix}.`;
    }
  } finally {
    state.ftpPreviewLoading.delete(prefix);
    state.ftpPreviewBackgroundLoading.delete(prefix);
    const currentPhoto = state.loadedPhotos.get(prefix);
    if (background && selectedSlotSource(prefix, currentPhoto) !== "ftp") {
      setFtpBadgeLoading(prefix, false);
    } else {
      updateSlotPreview(prefix);
    }
  }
}

function nextBackgroundFtpPreviewCandidate() {
  for (const slot of state.slots || []) {
    const prefix = slot.prefix;
    const photo = state.loadedPhotos.get(prefix);
    if (
      photo?.ftp &&
      photo.ftp_filename &&
      !photo.ftp_token &&
      !state.files.has(prefix) &&
      !state.deletedSlots.has(prefix) &&
      !photo?.dirty &&
      !state.ftpPreviewLoading.has(prefix)
    ) {
      return { prefix, photo };
    }
  }
  return null;
}

function scheduleBackgroundFtpPreviewLoad(requestId = state.photoLoadRequestId, delayMs = 900) {
  window.clearTimeout(state.backgroundFtpPreviewTimer);
  state.backgroundFtpPreviewTimer = window.setTimeout(() => {
    loadNextBackgroundFtpPreview(requestId).catch(() => {});
  }, delayMs);
}

async function loadNextBackgroundFtpPreview(requestId = state.photoLoadRequestId) {
  if (requestId !== state.photoLoadRequestId) {
    return;
  }
  let launched = 0;
  const limit = Math.max(1, Number(state.backgroundFtpPreviewLimit) || 1);
  while (state.ftpPreviewBackgroundLoading.size < limit) {
    const candidate = nextBackgroundFtpPreviewCandidate();
    if (!candidate) {
      break;
    }
    launched += 1;
    loadFtpPreview(candidate.photo, candidate.prefix, requestId, { background: true })
      .catch(() => {
        // Background preview loading must not block regular editing.
      })
      .finally(() => {
        if (requestId === state.photoLoadRequestId && nextBackgroundFtpPreviewCandidate()) {
          scheduleBackgroundFtpPreviewLoad(requestId, 900);
        }
      });
  }
  if (launched && requestId === state.photoLoadRequestId && nextBackgroundFtpPreviewCandidate()) {
    scheduleBackgroundFtpPreviewLoad(requestId, 900);
  }
}

function isSlotFit(prefix) {
  if (state.slotFits.has(prefix)) {
    return Boolean(state.slotFits.get(prefix));
  }
  return Boolean(state.defaultSlotFit);
}

function thumbnailUrl(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  const url =
    source === "ftp"
      ? photo?.ftp_thumb_url || photo?.ftp_url || ""
      : photo?.thumb_url || photo?.url || "";
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}fit=${isSlotFit(prefix) ? "1" : "0"}&width=260&height=180`;
}

function clearSlotAssignment(prefix, options = {}) {
  bumpSlotRevision(prefix);
  const markDelete = options.markDelete !== false;
  if (markDelete) {
    markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  }
  revokeFilePreviewUrl(prefix);
  state.files.delete(prefix);
  state.loadedPhotos.delete(prefix);
  state.slotFits.delete(prefix);
  state.slotSources.delete(prefix);
  state.userSelectedSlotSources.delete(prefix);
}

function setSlotFile(prefix, file, options = {}) {
  const validationError = uploadFileValidationError(file);
  bumpSlotRevision(prefix);
  markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  revokeFilePreviewUrl(prefix);
  const item = createSlotFileUpload(prefix, file, {
    provisional: options.provisional ?? isProvisionalSlotPlacement(prefix),
  });
  state.files.set(prefix, item);
  state.loadedPhotos.delete(prefix);
  state.slotSources.delete(prefix);
  state.userSelectedSlotSources.delete(prefix);
  if (validationError) {
    item.error = validationError;
    formStatus.textContent = `Blad uploadu slotu ${prefix}: ${item.error}`;
    updateSubmitButtonState();
    return item;
  }
  uploadSlotFile(prefix, item);
  return item;
}

function getSlotAssignment(prefix) {
  if (state.files.has(prefix)) {
    return { type: "file", prefix, value: state.files.get(prefix), source: "", fit: isSlotFit(prefix) };
  }
  if (state.loadedPhotos.has(prefix)) {
    const photo = state.loadedPhotos.get(prefix);
    return {
      type: "loaded",
      prefix,
      value: photo,
      source: transferableSlotSource(prefix, photo),
      fit: isSlotFit(prefix),
    };
  }
  return null;
}

function setSlotAssignment(prefix, assignment, options = {}) {
  const sourceFit = assignment && "fit" in assignment ? Boolean(assignment.fit) : isSlotFit(assignment?.prefix || prefix);
  const sourceType = assignment?.source || "";
  clearSlotAssignment(prefix, { markDelete: options.markDelete !== false });
  if (!assignment) {
    return;
  }
  if (assignment.type === "file") {
    const item = slotFileItem(assignment.value);
    if (item) {
      item.prefix = prefix;
      item.provisional = false;
      item.placementBlocked = false;
    }
    state.files.set(prefix, item);
    state.slotFits.set(prefix, sourceFit);
    if (sourceType) state.slotSources.set(prefix, sourceType);
    state.userSelectedSlotSources.delete(prefix);
    if (item?.file && !item.token && !item.uploading && !item.error) {
      uploadSlotFile(prefix, item);
    }
    return;
  }
  if (assignment.type === "loaded") {
    state.loadedPhotos.set(prefix, { ...assignment.value, prefix, dirty: true });
    state.slotFits.set(prefix, sourceFit);
    if (sourceType) state.slotSources.set(prefix, sourceType);
    state.userSelectedSlotSources.delete(prefix);
  }
}

function moveSlotContent(sourcePrefix, targetPrefix) {
  if (!sourcePrefix || !targetPrefix || sourcePrefix === targetPrefix) {
    return;
  }
  const source = getSlotAssignment(sourcePrefix);
  if (!source) {
    return;
  }
  const target = getSlotAssignment(targetPrefix);
  if (target) {
    markSlotDeletion(targetPrefix, state.loadedPhotos.get(targetPrefix));
    markSlotDeletion(sourcePrefix, state.loadedPhotos.get(sourcePrefix));
    clearSlotAssignment(targetPrefix, { markDelete: false });
    clearSlotAssignment(sourcePrefix, { markDelete: false });
    setSlotAssignment(targetPrefix, source, { markDelete: false });
    setSlotAssignment(sourcePrefix, target, { markDelete: false });
    formStatus.textContent = `Zamieniono slot ${sourcePrefix} ze slotem ${targetPrefix}.`;
    renderSlot(targetPrefix);
    renderSlot(sourcePrefix);
    return;
  }
  markSlotDeletion(targetPrefix, state.loadedPhotos.get(targetPrefix));
  markSlotDeletion(sourcePrefix, state.loadedPhotos.get(sourcePrefix));
  setSlotAssignment(targetPrefix, source, { markDelete: false });
  clearSlotAssignment(sourcePrefix, { markDelete: false });
  formStatus.textContent = `Przeniesiono slot ${sourcePrefix} -> ${targetPrefix}.`;
  renderSlot(targetPrefix);
  renderSlot(sourcePrefix);
}

function slotIndex(prefix) {
  return (state.slots || []).findIndex((slot) => String(slot.prefix) === String(prefix));
}

function slotPrefixAt(index) {
  return state.slots?.[index]?.prefix || "";
}

function isSlotFreeForNewFile(prefix) {
  return Boolean(prefix && !state.files.has(prefix) && !photoHasUsableContent(state.loadedPhotos.get(prefix)));
}

function nextFreeSlotPrefix(startPrefix, options = {}) {
  const start = slotIndex(startPrefix);
  if (start < 0) return "";
  const from = start + (options.after ? 1 : 0);
  for (let index = from; index < (state.slots || []).length; index += 1) {
    const prefix = slotPrefixAt(index);
    if (isSlotFreeForNewFile(prefix)) {
      return prefix;
    }
  }
  return "";
}

function warnNoFreeSlots(files, context = "") {
  const names = [...(files || [])]
    .map((file) => (typeof file === "string" ? file : file?.name || slotFileName(file)))
    .filter(Boolean);
  if (!names.length) return;
  const message =
    names.length === 1
      ? `Brak wolnego slotu dla pliku: ${names[0]}.`
      : `Brak wolnych slotow dla plikow: ${names.join(", ")}.`;
  formStatus.textContent = context ? `${message} ${context}` : message;
  window.alert(formStatus.textContent);
}

function uploadFileExtension(file) {
  const name = String(file?.name || slotFileName(file) || "").trim();
  const match = name.match(/\.([a-z0-9]+)$/i);
  return match ? match[1].toLowerCase() : "";
}

function uploadFileValidationError(file) {
  const extension = uploadFileExtension(file);
  const security = currentSecuritySettings();
  const allowed = normalizeUploadExtensionList(security.allowed_upload_extensions);
  const blocked = normalizeUploadExtensionList(security.blocked_upload_extensions);
  if (!extension) {
    return "Format niedozwolony: plik musi miec rozszerzenie.";
  }
  if (blocked.includes(extension)) {
    return `Format niedozwolony: .${extension} jest na czarnej liscie.`;
  }
  if (security.block_executable_uploads !== false && CLIENT_EXECUTABLE_UPLOAD_EXTENSIONS.has(extension)) {
    return `Format niedozwolony: .${extension} jest plikiem wykonywalnym.`;
  }
  if (allowed.length && !allowed.includes(extension)) {
    return `Format niedozwolony: .${extension} nie jest na bialej liscie.`;
  }
  return "";
}

function fileListFromInput(files) {
  return Array.from(files || []).filter(Boolean);
}

function assignFilesFromSlot(startPrefix, files, options = {}) {
  const incoming = fileListFromInput(files);
  if (!incoming.length) return;
  const assigned = [];
  const unassigned = [];
  const rejected = [];
  let searchPrefix = startPrefix;
  if (options.replaceStart && incoming.length === 1) {
    const item = setSlotFile(startPrefix, incoming[0], { provisional: isProvisionalSlotPlacement(startPrefix) });
    renderSlot(startPrefix);
    formStatus.textContent = slotUploadError(item)
      ? `Blad uploadu slotu ${startPrefix}: ${slotUploadError(item)}`
      : `Dodano plik do slotu ${startPrefix}.`;
    return;
  }
  for (const file of incoming) {
    const targetPrefix = nextFreeSlotPrefix(searchPrefix, { after: false });
    if (!targetPrefix) {
      unassigned.push(file);
      continue;
    }
    const item = setSlotFile(targetPrefix, file, { provisional: isProvisionalSlotPlacement(targetPrefix) });
    assigned.push({ prefix: targetPrefix, file, item });
    if (slotUploadError(item)) {
      rejected.push({ prefix: targetPrefix, file, item });
    }
    searchPrefix = slotPrefixAt(slotIndex(targetPrefix) + 1) || targetPrefix;
  }
  for (const item of assigned) {
    renderSlot(item.prefix);
  }
  if (rejected.length) {
    const first = rejected[0];
    formStatus.textContent =
      rejected.length === 1
        ? `Blad uploadu slotu ${first.prefix}: ${slotUploadError(first.item)}`
        : `Odrzucono ${rejected.length} plikow przed uploadem. Pierwszy blad: slot ${first.prefix}: ${slotUploadError(first.item)}`;
  } else if (assigned.length) {
    const targetText = assigned.map((item) => item.prefix).join(", ");
    formStatus.textContent =
      assigned.length === 1
        ? `Dodano plik do slotu ${targetText}.`
        : `Dodano ${assigned.length} plikow do slotow: ${targetText}.`;
  }
  if (unassigned.length) {
    warnNoFreeSlots(unassigned);
  }
}

function applyDefaultSlotSource(prefix, photo) {
  const source = defaultSlotSource(photo);
  if (!state.userSelectedSlotSources.has(prefix)) {
    if (source) {
      state.slotSources.set(prefix, source);
    } else {
      state.slotSources.delete(prefix);
    }
  } else if (!selectedSlotSource(prefix, photo)) {
    if (source) {
      state.slotSources.set(prefix, source);
    } else {
      state.slotSources.delete(prefix);
    }
    state.userSelectedSlotSources.delete(prefix);
  }
}

function relocateProvisionalSlotFile(prefix) {
  const item = state.files.get(prefix);
  if (!item?.provisional) {
    return [];
  }
  const targetPrefix = nextFreeSlotPrefix(prefix, { after: true });
  if (!targetPrefix) {
    if (!item.placementBlocked) {
      warnNoFreeSlots([slotFileName(item)], `Slot ${prefix} ma juz dane.`);
    }
    item.placementBlocked = true;
    return [prefix];
  }
  const sourceFit = isSlotFit(prefix);
  state.files.delete(prefix);
  revokeFilePreviewUrl(prefix);
  item.prefix = targetPrefix;
  item.provisional = isProvisionalSlotPlacement(targetPrefix);
  item.placementBlocked = false;
  state.files.set(targetPrefix, item);
  state.slotFits.delete(prefix);
  state.slotFits.set(targetPrefix, sourceFit);
  formStatus.textContent = `Slot ${prefix} ma juz dane. Przeniesiono ${slotFileName(item)} do slotu ${targetPrefix}.`;
  return [prefix, targetPrefix];
}

function updateSlotPreview(prefix) {
  const card = slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`);
  if (!card) {
    renderSlots();
    return;
  }
  const loadedPhoto = state.loadedPhotos.get(prefix);
  const selectedFile = state.files.get(prefix);
  const detail = card.querySelector(".slot-meta span");
  const preview = card.querySelector(".slot-preview");
  const previewImage = preview.querySelector("img");
  const empty = preview.querySelector(".slot-empty");
  const fitButton = card.querySelector(".slot-fit-button");
  card.dataset.activeSource = selectedSlotSource(prefix, loadedPhoto) || "";
  detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto, prefix);
  card.querySelectorAll(".slot-badge[data-source]").forEach((badge) => {
    const selected = selectedSlotSource(prefix, loadedPhoto) === badge.dataset.source;
    const loading =
      isPhotoSourceLoading(badge.dataset.source) ||
      (badge.dataset.source === "ftp" && state.ftpPreviewLoading.has(prefix));
    const titleBySource = {
      local: "Plik jest w folderze backendu",
      ftp: "Wpis dla slotu jest na FTP",
      sql: "Wpis dla slotu jest w SQL",
    };
    const sqlValue = String(loadedPhoto?.sql_value || "").trim();
    badge.classList.toggle("selected", selected);
    badge.classList.toggle("loading", loading);
    badge.setAttribute("aria-pressed", selected ? "true" : "false");
    if (loading) {
      badge.setAttribute("aria-busy", "true");
      badge.title = sourceLoadingTitle(badge.dataset.source);
    } else {
      badge.removeAttribute("aria-busy");
      const baseTitle =
        badge.dataset.source === "sql" && sqlValue
          ? "Kliknij, aby skopiowac link z SQL"
          : titleBySource[badge.dataset.source] || "";
      badge.title = selected ? `${baseTitle} (aktywny podglad)` : baseTitle;
    }
  });
  if (fitButton) {
    fitButton.classList.toggle("active", isSlotFit(prefix));
  }
  preview.classList.remove("has-image", "thumb-loading", "loaded-photo");
  preview.querySelector(".slot-upload-overlay")?.remove();
  previewImage.removeAttribute("src");
  empty.textContent = "Brak pliku";
  if (selectedFile) {
    if (isFileImageLike(selectedFile)) {
      renderSelectedFilePreview(prefix, selectedFile, preview, previewImage, empty);
    } else {
      empty.textContent = slotFileName(selectedFile);
    }
    renderSlotUploadOverlay(preview, selectedFile);
    return;
  }
  if (!loadedPhoto) return;
  preview.classList.add("loaded-photo");
  if (
    state.ftpPreviewLoading.has(prefix) &&
    !state.ftpPreviewBackgroundLoading.has(prefix) &&
    selectedSlotSource(prefix, loadedPhoto) === "ftp"
  ) {
    empty.textContent = "Pobieranie z FTP...";
    preview.classList.add("thumb-loading");
    return;
  }
  const thumb = thumbnailUrl(loadedPhoto, prefix);
  if (thumb && loadedPhoto.is_image) {
    preview.classList.add("thumb-loading");
    previewImage.addEventListener(
      "load",
      () => {
        preview.classList.remove("thumb-loading");
      },
      { once: true }
    );
    previewImage.addEventListener(
      "error",
      () => {
        preview.classList.remove("thumb-loading", "has-image");
        empty.textContent = "Podglad niedostepny";
      },
      { once: true }
    );
    previewImage.src = thumb;
    preview.classList.add("has-image");
    return;
  }
  empty.textContent =
    selectedSlotSource(prefix, loadedPhoto) === "ftp" && loadedPhoto.ftp_filename && !loadedPhoto.ftp_token
      ? "Kliknij FTP, aby pobrac podglad"
      : slotStatusText(loadedPhoto, prefix);
}

function createSlotNode(slot) {
    const node = slotTemplate.content.firstElementChild.cloneNode(true);
    const title = node.querySelector(".slot-meta strong");
    const detail = node.querySelector(".slot-meta span");
    const input = node.querySelector("input");
    const preview = node.querySelector(".slot-preview");
    const previewImage = node.querySelector("img");
    const empty = node.querySelector(".slot-empty");
    const meta = node.querySelector(".slot-meta");
    const loadedPhoto = state.loadedPhotos.get(slot.prefix);
    const selectedFile = state.files.get(slot.prefix);
    const overlay = document.createElement("div");
    const controls = document.createElement("div");
    const fitButton = document.createElement("button");
    const openButton = document.createElement("button");
    const clearButton = document.createElement("button");
    node.dataset.slotPrefix = slot.prefix;
    node.dataset.activeSource = selectedSlotSource(slot.prefix, loadedPhoto) || "";

    title.textContent = `${slot.prefix} - ${slot.label}`;
    detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto, slot.prefix);
    input.name = `slot_${slot.prefix}`;
    input.multiple = true;
    input.accept = uploadAcceptAttribute();
    previewImage.draggable = false;
    previewImage.loading = "lazy";
    previewImage.decoding = "async";
    node.draggable = Boolean(selectedFile || loadedPhoto?.token || loadedPhoto?.ftp_token || loadedPhoto?.ftp_filename);
    renderSlotBadges(meta, loadedPhoto, selectedFile, slot.prefix);
    overlay.className = "slot-loading-overlay";
    overlay.innerHTML = `<span>${photoLoadingText()}</span><div class="progress-line"><i></i></div>`;
    if (state.photosLoading && !selectedFile && !loadedPhoto) {
      preview.appendChild(overlay);
    }
    controls.className = "slot-controls";
    fitButton.type = "button";
    fitButton.className = `slot-fit-button ${isSlotFit(slot.prefix) ? "active" : ""}`;
    fitButton.textContent = "FIT";
    fitButton.title = "Dopasuj zapis tego slotu do zawartosci obrazu";
    fitButton.addEventListener("click", (event) => {
      event.stopPropagation();
      state.slotFits.set(slot.prefix, !isSlotFit(slot.prefix));
      updateSlotPreview(slot.prefix);
    });
    openButton.type = "button";
    openButton.className = "slot-open-button";
    openButton.textContent = "Otworz";
    openButton.title = "Otworz oryginalny plik z tego slotu";
    openButton.addEventListener("click", (event) => {
      event.stopPropagation();
      openSlotFile(slot.prefix).catch((error) => {
        formStatus.textContent = error.message;
      });
    });
    clearButton.type = "button";
    clearButton.className = "slot-clear-button";
    clearButton.textContent = "Usun";
    clearButton.title = "Usun plik z tego slotu w formularzu";
    clearButton.addEventListener("click", (event) => {
      event.stopPropagation();
      const hadSavedPhoto = Boolean(state.loadedPhotos.get(slot.prefix));
      clearSlotAssignment(slot.prefix);
      formStatus.textContent = hadSavedPhoto
        ? `Oznaczono slot ${slot.prefix} do usuniecia przy zapisie.`
        : `Wyczyszczono slot ${slot.prefix}.`;
      renderSlot(slot.prefix);
    });
    if (selectedFile || loadedPhoto) {
      const hasOpenableFile =
        Boolean(selectedFile) ||
        Boolean(selectedPhotoToken(loadedPhoto, slot.prefix)) ||
        Boolean(loadedPhoto?.ftp_filename);
      const hasFittablePreview =
        (selectedFile && isFileImageLike(selectedFile)) ||
        (loadedPhoto?.is_image && (selectedPhotoToken(loadedPhoto, slot.prefix) || loadedPhoto?.ftp_filename));
      if (hasFittablePreview) {
        controls.appendChild(fitButton);
      }
      if (hasOpenableFile) {
        controls.appendChild(openButton);
      }
      controls.appendChild(clearButton);
      meta.appendChild(controls);
    }

    if (selectedFile) {
      if (isFileImageLike(selectedFile)) {
        renderSelectedFilePreview(slot.prefix, selectedFile, preview, previewImage, empty);
      } else {
        empty.textContent = slotFileName(selectedFile);
      }
      renderSlotUploadOverlay(preview, selectedFile);
    } else if (loadedPhoto) {
      preview.classList.add("loaded-photo");
      const thumb = thumbnailUrl(loadedPhoto, slot.prefix);
      if (
        state.ftpPreviewLoading.has(slot.prefix) &&
        !state.ftpPreviewBackgroundLoading.has(slot.prefix) &&
        selectedSlotSource(slot.prefix, loadedPhoto) === "ftp"
      ) {
        preview.classList.add("thumb-loading");
        empty.textContent = "Pobieranie z FTP...";
      } else if (thumb && loadedPhoto.is_image) {
        preview.classList.add("thumb-loading");
        previewImage.addEventListener("load", () => {
          preview.classList.remove("thumb-loading");
        });
        previewImage.addEventListener("error", () => {
          preview.classList.remove("thumb-loading", "has-image");
          empty.textContent = "Podglad niedostepny";
        });
        previewImage.src = thumb;
        preview.classList.add("has-image");
      } else {
        empty.textContent =
          selectedSlotSource(slot.prefix, loadedPhoto) === "ftp" && loadedPhoto.ftp_filename && !loadedPhoto.ftp_token
            ? "Kliknij FTP, aby pobrac podglad"
            : slotStatusText(loadedPhoto, slot.prefix);
      }
    }

    node.addEventListener("dragstart", (event) => {
      const assignment = getSlotAssignment(slot.prefix);
      if (!assignment) {
        event.preventDefault();
        return;
      }
      state.draggedSlotPrefix = slot.prefix;
      event.dataTransfer.setData("application/x-picorg-slot", slot.prefix);
      event.dataTransfer.setData("text/plain", slot.prefix);
      event.dataTransfer.effectAllowed = "move";
    });
    node.addEventListener("dragover", (event) => {
      event.preventDefault();
      node.classList.add("drag-over");
      const sourcePrefix =
        event.dataTransfer.getData("application/x-picorg-slot") ||
        state.draggedSlotPrefix ||
        event.dataTransfer.getData("text/plain");
      event.dataTransfer.dropEffect = sourcePrefix ? "move" : "copy";
    });
    node.addEventListener("dragleave", () => {
      node.classList.remove("drag-over");
    });
    node.addEventListener("dragend", () => {
      state.draggedSlotPrefix = "";
      node.classList.remove("drag-over");
    });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drag-over");
      const sourcePrefix =
        event.dataTransfer.getData("application/x-picorg-slot") ||
        state.draggedSlotPrefix ||
        event.dataTransfer.getData("text/plain");
      if (sourcePrefix && getSlotAssignment(sourcePrefix)) {
        state.draggedSlotPrefix = "";
        moveSlotContent(sourcePrefix, slot.prefix);
        return;
      }
      const files = fileListFromInput(event.dataTransfer.files);
      if (files.length) {
        state.draggedSlotPrefix = "";
        assignFilesFromSlot(slot.prefix, files);
      }
    });

    input.addEventListener("change", () => {
      const files = fileListFromInput(input.files);
      if (!files.length) {
        bumpSlotRevision(slot.prefix);
        revokeFilePreviewUrl(slot.prefix);
        state.files.delete(slot.prefix);
        renderSlot(slot.prefix);
        return;
      }
      assignFilesFromSlot(slot.prefix, files, { replaceStart: true });
      input.value = "";
    });

    return node;
}

function renderSlot(prefix) {
  const slot = (state.slots || []).find((item) => String(item.prefix) === String(prefix));
  const existing = slotGrid.querySelector(`[data-slot-prefix="${prefix}"]`);
  if (!slot || !existing) {
    renderSlots();
    return;
  }
  existing.replaceWith(createSlotNode(slot));
  updateSubmitButtonState();
}

function renderChangedSlots(prefixes, options = {}) {
  const uniquePrefixes = [...new Set([...(prefixes || [])].map((prefix) => String(prefix || "")).filter(Boolean))];
  for (const prefix of uniquePrefixes) {
    if (options.skipPendingUserEdits && slotHasPendingUserEdit(prefix)) continue;
    renderSlot(prefix);
  }
}

function renderSlotsExceptPendingUserEdits(prefixes = null) {
  const targetPrefixes = prefixes
    ? [...prefixes]
    : (state.slots || []).map((slot) => slot.prefix);
  renderChangedSlots(targetPrefixes, { skipPendingUserEdits: true });
}

function renderSlots(slots = state.slots) {
  slotGrid.textContent = "";
  state.slots = slots;
  slotCount.textContent = `${slots.length} pol`;

  for (const slot of slots) {
    slotGrid.appendChild(createSlotNode(slot));
  }
  updateSubmitButtonState();
}

function renderListTabs() {
  listTabs.textContent = "";
  for (const [key, label] of Object.entries(listLabels)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${label} (${(state.lists[key] || []).length})`;
    button.classList.toggle("active", state.selectedList === key);
    button.addEventListener("click", () => {
      state.selectedList = key;
      state.listFilter = "";
      renderListEditor();
    });
    listTabs.appendChild(button);
  }
}

function normalizeListValue(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLocaleLowerCase("pl-PL");
}

function boundedEditDistance(a, b, maxDistance = 4) {
  if (Math.abs(a.length - b.length) > maxDistance) return maxDistance + 1;
  const previous = Array.from({ length: b.length + 1 }, (_, index) => index);
  const current = Array(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i += 1) {
    current[0] = i;
    let rowMin = current[0];
    for (let j = 1; j <= b.length; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
      rowMin = Math.min(rowMin, current[j]);
    }
    if (rowMin > maxDistance) return maxDistance + 1;
    for (let j = 0; j <= b.length; j += 1) previous[j] = current[j];
  }
  return previous[b.length];
}

function listMatch(value, query) {
  const normalized = normalizeListValue(value);
  const needle = normalizeListValue(query);
  if (!needle) {
    return { visible: true, rank: 9, distance: 0, className: "" };
  }
  if (normalized === needle) {
    return { visible: true, rank: 0, distance: 0, className: "exact-match" };
  }
  if (normalized.startsWith(needle)) {
    return { visible: true, rank: 1, distance: normalized.length - needle.length, className: "partial-match" };
  }
  if (normalized.includes(needle)) {
    return { visible: true, rank: 2, distance: normalized.length - needle.length, className: "partial-match" };
  }
  const maxDistance = needle.length <= 5 ? 2 : 4;
  const distance = boundedEditDistance(normalized, needle, maxDistance);
  if (distance <= maxDistance) {
    return { visible: true, rank: 3, distance, className: "similar-match" };
  }
  return { visible: false, rank: 99, distance: 99, className: "" };
}

function ensureListFilterInfo() {
  let info = document.querySelector("#listFilterInfo");
  if (!info) {
    info = document.createElement("div");
    info.id = "listFilterInfo";
    info.className = "list-filter-info";
    listAddForm.insertAdjacentElement("afterend", info);
  }
  return info;
}

function renderListEditor() {
  renderListTabs();
  listValues.textContent = "";
  listAddInput.value = state.listFilter;
  listAddInput.placeholder = `Nowa wartosc: ${listLabels[state.selectedList]}`;
  const info = ensureListFilterInfo();
  const query = state.listFilter;
  const values = state.lists[state.selectedList] || [];
  const rows = values
    .map((value, index) => ({ value, index, match: listMatch(value, query) }))
    .filter((item) => item.match.visible)
    .sort((left, right) => {
      if (!query) return left.index - right.index;
      return (
        left.match.rank - right.match.rank ||
        left.match.distance - right.match.distance ||
        left.value.localeCompare(right.value, "pl")
      );
    });
  const duplicate = Boolean(query) && values.some((value) => normalizeListValue(value) === normalizeListValue(query));
  if (query) {
    info.textContent = duplicate
      ? "Taka wartosc juz istnieje. Dodawanie duplikatu jest zablokowane."
      : `Pasujace wpisy: ${rows.length}. Enter doda nowa wartosc, jesli nie jest duplikatem.`;
    info.classList.toggle("duplicate", duplicate);
  } else {
    info.textContent = "";
    info.classList.remove("duplicate");
  }
  for (const { value, match } of rows) {
    const row = document.createElement("div");
    row.className = `list-value-row ${match.className}`;
    const text = document.createElement("span");
    const remove = document.createElement("button");
    text.textContent = value;
    if (match.rank === 3) {
      row.title = `Podobny wpis, roznica znakow: ${match.distance}`;
    }
    remove.type = "button";
    remove.className = "icon-button";
    remove.textContent = "X";
    remove.title = "Usun";
    remove.addEventListener("click", () => removeListValue(value));
    row.append(text, remove);
    listValues.appendChild(row);
  }
  if (!rows.length && query) {
    const empty = document.createElement("div");
    empty.className = "list-empty-filter";
    empty.textContent = "Brak podobnych wpisow.";
    listValues.appendChild(empty);
  }
}

function setBusy(isBusy, text = "") {
  if (submitButton) {
    submitButton.dataset.busy = isBusy ? "1" : "";
    submitButton.disabled = Boolean(isBusy);
  }
  formStatus.textContent = text;
  updateSubmitButtonState();
}

function stopProcessStatusTicker(text = "") {
  window.clearInterval(state.processStatusTimer);
  state.processStatusTimer = 0;
  state.processStatusStartedAt = 0;
  if (text) formStatus.textContent = text;
}

function startProcessStatusTicker(label, prefixes = new Set()) {
  stopProcessStatusTicker();
  const phaseTexts = [
    "backend zapisuje lokalne zmiany",
    "backend sprawdza brakujace zrodla",
    "backend synchronizuje FTP/SQL",
    "czekam na odpowiedz backendu",
  ];
  const changed = [...prefixes].filter(Boolean).sort();
  const slotText = changed.length ? ` Sloty: ${changed.join(", ")}.` : "";
  let step = 0;
  state.processStatusStartedAt = performance.now();
  const render = () => {
    const elapsed = Math.max(1, Math.round((performance.now() - state.processStatusStartedAt) / 1000));
    const phase = phaseTexts[Math.min(step, phaseTexts.length - 1)];
    formStatus.textContent = `${label}: ${phase} (${elapsed} s).${slotText}`;
    step += 1;
  };
  render();
  state.processStatusTimer = window.setInterval(render, 5000);
}

function clearResult() {
  resultMeta.textContent = "";
  resultOutput.className = "result-output empty-state";
  resultOutput.textContent = "Brak aktywnych pomiarow.";
}

function showError(error) {
  resultMeta.textContent = "";
  resultOutput.className = "result-output error-text";
  resultOutput.textContent = error.message || String(error);
}

function processingOperationLabel(operation) {
  const labels = {
    copy_preprocessed: "kopiowanie po obrobce",
    copy_without_processing: "kopiowanie bez obrobki",
    copy_document: "kopiowanie dokumentu",
    copy_unsupported_image: "kopiowanie formatu bez obrobki",
    copy_no_pillow: "kopiowanie bez Pillow",
    process_image: "resize/kompresja",
    same_target: "bez kopiowania",
  };
  return labels[operation] || operation || "plik";
}

function renderTimingDetails(timing, savedFiles = []) {
  const stages = timing?.stages || [];
  const files = savedFiles || [];
  if (!stages.length && !files.length) return null;
  const box = document.createElement("details");
  const summary = document.createElement("summary");
  const list = document.createElement("div");
  box.className = "timing-details";
  summary.textContent = `Czas operacji: ${formatDuration(timing?.total_ms)}`;
  list.className = "timing-list";
  for (const stage of stages) {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("strong");
    const details = stage.details || {};
    const detailText =
      stage.key === "antivirus_scan"
        ? ` (${details.enabled ? "wlaczony" : "wylaczony"}, skan: ${details.scanned || 0})`
        : "";
    label.textContent = `${stage.label || stage.key || "Etap"}${detailText}`;
    value.textContent = formatDuration(stage.elapsed_ms);
    row.append(label, value);
    list.appendChild(row);
  }
  if (files.length) {
    const section = document.createElement("div");
    section.className = "timing-section";
    section.textContent = "Pliki";
    list.appendChild(section);
  }
  for (const file of files) {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("strong");
    const flags = [];
    if (file.preprocessed) flags.push("preprocessed");
    if (file.content_fit) flags.push("FIT");
    const sizes =
      file.source_size_bytes || file.size_bytes
        ? ` (${formatFileSize(file.source_size_bytes)} -> ${formatFileSize(file.size_bytes)})`
        : "";
    const suffix = flags.length ? `, ${flags.join(", ")}` : "";
    const operation = processingOperationLabel(file.operation);
    label.textContent = `${file.prefix || "Slot"} - ${operation}${suffix}${sizes}`;
    value.textContent = formatDuration(file.elapsed_ms);
    row.append(label, value);
    list.appendChild(row);
  }
  box.append(summary, list);
  return box;
}

function showResult(payload) {
  resultOutput.className = "result-output";
  resultOutput.textContent = "";
  resultMeta.textContent = payload.timing?.total_ms ? `Czas: ${formatDuration(payload.timing.total_ms)}` : "";
  if (payload.entry && payload.entry.product_id) {
    productForm.elements.product_id.value = payload.entry.product_id;
  }
  if (!productForm.elements.ean.value && payload.ean && payload.ean !== "BRAK-EAN") {
    productForm.elements.ean.value = payload.ean;
  }
  const timing = renderTimingDetails(payload.timing, []);
  if (timing) {
    resultOutput.appendChild(timing);
  } else {
    resultOutput.className = "result-output empty-state";
    resultOutput.textContent = "Brak danych pomiarowych.";
  }
}

function processJobIsActive(job = {}) {
  return ["queued", "running"].includes(job.status || "");
}

function processJobProblemMessages(job = {}) {
  if (job.status === "failed") {
    return [job.error || "Zadanie nie powiodlo sie."];
  }
  return job.warning_messages || [];
}

function entryFromProcessJob(job = {}) {
  if (job.result) {
    return entryFromProcessPayload(job.result, job.entry || {});
  }
  const entry = { ...(job.entry || {}) };
  entry.label = productEntryLabel(entry);
  return entry;
}

function closeProcessAlert() {
  processAlertModal?.classList.remove("active");
  if (processAlertLoadButton) {
    processAlertLoadButton.dataset.jobId = "";
  }
}

function showProcessJobAlert(job = {}) {
  if (!processAlertModal || state.acknowledgedProcessAlerts.has(job.job_id)) {
    return;
  }
  const messages = processJobProblemMessages(job);
  if (!messages.length) {
    return;
  }
  state.acknowledgedProcessAlerts.add(job.job_id);
  if (processAlertTitle) {
    processAlertTitle.textContent =
      job.status === "failed" ? "Zadanie nie powiodlo sie" : "Zadanie zakonczone z ostrzezeniem";
  }
  if (processAlertEntry) {
    processAlertEntry.textContent = `Wpis: ${job.entry_label || productEntryLabel(job.entry || {}) || "bez danych"}`;
  }
  if (processAlertMessage) {
    processAlertMessage.textContent = messages.join(" | ");
  }
  if (processAlertLoadButton) {
    processAlertLoadButton.dataset.jobId = job.job_id || "";
    processAlertLoadButton.disabled = !job.entry;
  }
  processAlertModal.classList.add("active");
}

function showQueuedProcess(job = {}) {
  resultMeta.textContent = "Kolejka";
  resultOutput.className = "result-output";
  resultOutput.textContent = "";
  const message = document.createElement("p");
  message.className = "ok-text";
  message.textContent = `Przyjeto zadanie dla wpisu: ${
    job.entry_label || productEntryLabel(job.entry || {}) || "bez danych"
  }. Pomiary beda aktualizowane podczas pracy kolejki.`;
  resultOutput.appendChild(message);
}

function clampProgress(value) {
  return Math.max(0, Math.min(100, Math.round(Number(value || 0))));
}

function processQueueMeta(job = {}) {
  const user = job.username ? `uzytkownik: ${job.username}` : "";
  if (job.status === "running") {
    return ["Teraz", user].filter(Boolean).join(" | ");
  }
  const position = Number(job.queue_position || 0);
  return [`W kolejce${position ? ` #${position}` : ""}`, user].filter(Boolean).join(" | ");
}

function processQueueElapsedMs(job = {}, payload = state.processQueue, key = "started_at") {
  const reference = Number(payload.server_time || Date.now() / 1000);
  const started = Number(job[key] || 0);
  return started > 0 ? Math.max(0, Math.round((reference - started) * 1000)) : 0;
}

function processMetricRow(labelText, valueText, options = {}) {
  const row = document.createElement("div");
  const label = document.createElement("span");
  const value = document.createElement("strong");
  if (options.wide) {
    row.className = "wide";
  }
  label.textContent = labelText;
  value.textContent = valueText;
  row.append(label, value);
  return row;
}

function renderProcessMeasurements(payload = state.processQueue) {
  if (!resultOutput || !resultMeta) {
    return;
  }
  applyTimingDetailsVisibility();
  if (!showTimingDetails()) {
    return;
  }
  const jobs = payload.jobs || [];
  const current = jobs.find((job) => job.status === "running");
  resultOutput.textContent = "";
  if (!jobs.length) {
    resultMeta.textContent = "";
    resultOutput.className = "result-output empty-state";
    resultOutput.textContent = "Brak aktywnych pomiarow.";
    return;
  }
  resultOutput.className = "result-output";
  const metrics = document.createElement("div");
  metrics.className = "timing-list";
  if (current) {
    const stages = current.timing?.stages || [];
    resultMeta.textContent = `${clampProgress(current.progress)}% | czeka: ${payload.queued_count || 0}`;
    metrics.append(
      processMetricRow("Aktualny towar", current.entry_label || "zadanie", { wide: true }),
      processMetricRow("Etap", current.progress_label || "Trwa"),
      processMetricRow("Czas zadania", formatDuration(processQueueElapsedMs(current, payload, "started_at"))),
      processMetricRow("Czas od zlecenia", formatDuration(processQueueElapsedMs(current, payload, "created_at"))),
      processMetricRow("Oczekuje w kolejce", String(payload.queued_count || 0))
    );
    if (stages.length) {
      const section = document.createElement("div");
      section.className = "timing-section";
      section.textContent = "Czynnosci";
      metrics.appendChild(section);
      for (const stage of stages) {
        metrics.appendChild(
          processMetricRow(
            stage.running ? `${stage.label || stage.key} (trwa)` : stage.label || stage.key || "Etap",
            timingMs(stage.elapsed_ms)
          )
        );
      }
    }
  } else {
    const first = jobs[0] || {};
    resultMeta.textContent = `Czeka: ${payload.queued_count || jobs.length}`;
    metrics.append(
      processMetricRow("Pierwszy w kolejce", first.entry_label || "zadanie", { wide: true }),
      processMetricRow("Czas oczekiwania", formatDuration(processQueueElapsedMs(first, payload, "created_at"))),
      processMetricRow("Liczba zadan", String(jobs.length))
    );
  }
  resultOutput.appendChild(metrics);
}

function renderProcessQueue(payload = state.processQueue) {
  if (!processQueuePanel || !processQueueList || !processQueueSummary) {
    return;
  }
  const jobs = payload.jobs || [];
  state.processQueue = payload;
  processQueuePanel.classList.toggle("empty", !jobs.length);
  processQueueList.textContent = "";
  if (!jobs.length) {
    processQueueSummary.textContent = "Brak zadan";
    processQueueList.className = "process-queue-list empty-state";
    processQueueList.textContent = "Kolejka pusta.";
    renderProcessMeasurements(payload);
    return;
  }
  const current = jobs.find((job) => job.status === "running");
  processQueueSummary.textContent = current
    ? `Teraz: ${current.entry_label || "zadanie"} | czeka: ${payload.queued_count || 0}`
    : `Czeka: ${payload.queued_count || jobs.length}`;
  processQueueList.className = "process-queue-list";
  for (const job of jobs) {
    const item = document.createElement("article");
    const meta = document.createElement("div");
    const title = document.createElement("strong");
    const stage = document.createElement("span");
    const progressLine = document.createElement("div");
    const progressBar = document.createElement("i");
    const progressText = document.createElement("small");
    const progress = clampProgress(job.progress);
    item.className = `process-queue-item process-queue-${job.status || "queued"}`;
    meta.className = "process-queue-meta";
    meta.textContent = processQueueMeta(job);
    title.textContent = job.entry_label || productEntryLabel(job.entry || {}) || "Zadanie bez nazwy";
    stage.textContent =
      job.progress_label || processStatusLabels[job.status] || job.status || "Zadanie";
    progressLine.className = "process-queue-progress";
    progressLine.style.setProperty("--queue-progress", `${progress}%`);
    progressText.textContent = `${progress}%`;
    progressLine.appendChild(progressBar);
    item.append(meta, title, stage, progressLine, progressText);
    processQueueList.appendChild(item);
  }
  renderProcessMeasurements(payload);
}

async function refreshProcessQueue() {
  const payload = await requestJson("/api/process-jobs/active");
  renderProcessQueue(payload);
}

function updateProcessJobFromPayload(job = {}) {
  if (!job.job_id) return;
  const previous = state.processJobs.get(job.job_id) || {};
  const merged = { ...previous, ...job };
  state.processJobs.set(job.job_id, merged);
  if (processJobIsActive(merged)) {
    return;
  }
  if (merged.result) {
    upsertProductEntry(entryFromProcessJob(merged));
    if (merged.result.file_index) {
      state.fileIndex = merged.result.file_index;
      updateRuntimeMetrics();
    }
  }
  const messages = processJobProblemMessages(merged);
  if (messages.length) {
    showProcessJobAlert(merged);
    formStatus.textContent = `Zadanie w tle ma problem: ${messages[0]}`;
  } else if (!hasProductDraftData()) {
    formStatus.textContent = `Zadanie w tle zakonczone: ${merged.entry_label || "wpis"}.`;
  }
}

function scheduleProcessJobPoll(delay = 1500) {
  if (state.processJobPollTimer) {
    if (delay > 0) {
      return;
    }
    window.clearTimeout(state.processJobPollTimer);
    state.processJobPollTimer = 0;
  }
  state.processJobPollTimer = window.setTimeout(() => {
    state.processJobPollTimer = 0;
    pollProcessJobs().catch(() => {});
  }, delay);
}

async function pollProcessJobs() {
  if (document.hidden) {
    scheduleProcessJobPoll(POLL_HIDDEN_DELAY_MS);
    return;
  }
  const active = [...state.processJobs.values()].filter(processJobIsActive);
  if (!active.length) {
    return;
  }
  for (const job of active) {
    try {
      const payload = await requestJson(`/api/process-jobs/${encodeURIComponent(job.job_id)}`);
      updateProcessJobFromPayload(payload);
    } catch (error) {
      const failed = {
        ...job,
        status: "failed",
        error: error.message || "Nie udalo sie sprawdzic statusu zadania.",
      };
      updateProcessJobFromPayload(failed);
    }
  }
  if ([...state.processJobs.values()].some(processJobIsActive)) {
    scheduleProcessJobPoll();
  }
}

function trackProcessJob(job = {}) {
  if (!job.job_id) {
    return;
  }
  state.processJobs.set(job.job_id, job);
  scheduleProcessJobPoll();
}

async function loadRecentProcessJobs() {
  const payload = await requestJson("/api/process-jobs?limit=10");
  for (const job of payload.jobs || []) {
    if (processJobIsActive(job)) {
      trackProcessJob(job);
    } else if (processJobProblemMessages(job).length) {
      updateProcessJobFromPayload(job);
    }
  }
}

function entryFromHistoryGroup(group) {
  for (const item of group.items || []) {
    if (item.details?.entry) return item.details.entry;
  }
  return {};
}

function entryField(entry, ...keys) {
  for (const key of keys) {
    const value = entry?.[key];
    if (value) return value;
  }
  return "";
}

function historyEntryLabel(entry) {
  const colors = [
    entryField(entry, "KOLOR1", "color1"),
    entryField(entry, "KOLOR2", "color2"),
    entryField(entry, "KOLOR3", "color3"),
  ]
    .filter(Boolean)
    .join(" / ");
  return [
    entryField(entry, "NAZWA", "name") ? `Nazwa: ${entryField(entry, "NAZWA", "name")}` : "",
    entryField(entry, "TYP", "type_name") ? `Typ: ${entryField(entry, "TYP", "type_name")}` : "",
    entryField(entry, "MODEL", "model") ? `Model: ${entryField(entry, "MODEL", "model")}` : "",
    colors ? `Kolory: ${colors}` : "",
    entryField(entry, "DODATKI", "extra") ? `Dodatek: ${entryField(entry, "DODATKI", "extra")}` : "",
  ]
    .filter(Boolean)
    .join(" | ");
}

function timingMs(value) {
  return `${Math.max(0, Math.round(Number(value || 0)))} ms`;
}

function renderHistoryTiming(item = {}) {
  if (!historyTimingTitle || !historyTimingOutput) {
    return;
  }
  const timing = item.details?.timing || {};
  historyTimingTitle.textContent = `Czasy: ${item.time || item.summary || "zmiana"}`;
  historyTimingOutput.textContent = "";
  const stages = timing.stages || [];
  historyTimingOutput.appendChild(processMetricRow("Razem", timingMs(timing.total_ms)));
  if (stages.length) {
    const section = document.createElement("div");
    section.className = "timing-section";
    section.textContent = "Czynnosci";
    historyTimingOutput.appendChild(section);
  }
  for (const stage of stages) {
    historyTimingOutput.appendChild(
      processMetricRow(stage.label || stage.key || "Etap", timingMs(stage.elapsed_ms))
    );
  }
  if (!stages.length && !timing.total_ms) {
    historyTimingOutput.className = "timing-list empty-state";
    historyTimingOutput.textContent = "Ta zmiana nie ma zapisanych pomiarow czasu.";
  } else {
    historyTimingOutput.className = "timing-list";
  }
  document.querySelector("#historyTimingModal")?.classList.add("active");
}

function renderHistoryDetails(group) {
  historyDetailTitle.textContent = `Historia EAN ${group.ean}`;
  historyDetailOutput.textContent = "";
  for (const item of group.items || []) {
    const row = document.createElement("article");
    const meta = document.createElement("div");
    const summary = document.createElement("strong");
    const details = document.createElement("span");
    const actions = document.createElement("div");
    const timingButton = document.createElement("button");
    row.className = "history-item";
    meta.className = "history-meta";
    meta.textContent = `${item.time || ""} | ${item.user || ""}`;
    summary.textContent = item.summary || item.action || "Zmiana";
    const saved = item.details?.saved_files?.length || 0;
    const deleted = item.details?.deleted_slots?.length || 0;
    const ftp = item.details?.ftp;
    const sql = item.details?.sql;
    details.textContent = [
      historyEntryLabel(item.details?.entry) || "",
      saved ? `zapisane pliki: ${saved}` : "",
      deleted ? `usuniete sloty: ${deleted}` : "",
      item.details?.local_delete?.deleted ? `usunieto lokalnie: ${item.details.local_delete.deleted}` : "",
      ftp?.enabled ? `FTP wyslano/usunieto: ${ftp.uploaded || 0}/${ftp.deleted || 0}${ftp.error ? `, blad: ${ftp.error}` : ""}` : "",
      sql?.enabled ? `SQL aktualizacje/czyszczenia: ${sql.updated || 0}/${sql.cleared || 0}${sql.error ? `, blad: ${sql.error}` : ""}` : "",
    ]
      .filter(Boolean)
      .join(" | ");
    actions.className = "history-item-actions";
    timingButton.type = "button";
    timingButton.className = "secondary-button";
    timingButton.textContent = "Czasy";
    timingButton.disabled = !item.details?.timing;
    timingButton.addEventListener("click", () => renderHistoryTiming(item));
    actions.appendChild(timingButton);
    row.append(meta, summary, details, actions);
    historyDetailOutput.appendChild(row);
  }
  document.querySelector("#historyDetailModal").classList.add("active");
}

function updateHistoryPagination(payload) {
  if (!historyPageInfo) {
    return;
  }
  const page = Number(payload.page || 1);
  const totalPages = Number(payload.total_pages || 1);
  const totalGroups = Number(payload.total_groups || 0);
  historyPageInfo.textContent = `Strona ${page}/${totalPages} | wpisy: ${totalGroups}`;
  if (historyPrevButton) {
    historyPrevButton.disabled = page <= 1;
  }
  if (historyNextButton) {
    historyNextButton.disabled = page >= totalPages;
  }
}

function renderHistory(payload) {
  state.history = payload;
  state.historyPage = Number(payload.page || state.historyPage || 1);
  const selectedUser = historyUserFilter.value;
  historyUserFilter.textContent = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "Wszyscy uzytkownicy";
  historyUserFilter.appendChild(all);
  for (const user of payload.users || []) {
    const option = document.createElement("option");
    option.value = user;
    option.textContent = user;
    option.selected = user === selectedUser;
    historyUserFilter.appendChild(option);
  }
  historyOutput.textContent = "";
  updateHistoryPagination(payload);
  const groups = payload.groups || [];
  if (!groups.length) {
    historyOutput.className = "history-output empty-state";
    historyOutput.textContent = "Brak historii dla wybranego filtra.";
    return;
  }
  historyOutput.className = "history-output";
  for (const group of groups) {
    const entry = entryFromHistoryGroup(group);
    const row = document.createElement("button");
    const title = document.createElement("strong");
    const fields = document.createElement("span");
    const meta = document.createElement("small");
    row.type = "button";
    row.className = "history-summary-row";
    title.textContent = `EAN ${group.ean}`;
    const readableFields = historyEntryLabel(entry);
    fields.textContent = readableFields || "Brak danych pol tekstowych";
    meta.textContent = `${(group.items || []).length} zmian | ostatnio: ${group.items?.[0]?.time || ""}`;
    row.append(title, fields, meta);
    row.addEventListener("click", () => renderHistoryDetails(group));
    historyOutput.appendChild(row);
  }
}

async function loadHistory(options = {}) {
  const page = Math.max(1, Number(options.page || state.historyPage || 1));
  state.historyPage = page;
  const params = new URLSearchParams({
    user: historyUserFilter?.value || "",
    query: historySearchInput?.value || "",
    page: String(page),
    page_size: String(state.historyPageSize || 50),
    limit: "1000",
  });
  const payload = await requestJson(`/api/history?${params.toString()}`);
  renderHistory(payload);
}

function showHistoryLoadError(error) {
  if (historyOutput) {
    historyOutput.className = "history-output empty-state";
    historyOutput.textContent = error.message;
  }
}

function logReadStorageKey() {
  const username = state.currentUser?.username || "anonymous";
  return `picorg-log-read-${username}`;
}

function readLogMarker() {
  try {
    return JSON.parse(localStorage.getItem(logReadStorageKey()) || "{}");
  } catch (_error) {
    return {};
  }
}

function writeLogMarker(summary = {}) {
  const marker = {
    critical: summary.latest_critical_id || "",
    warning: summary.latest_warning_id || "",
  };
  localStorage.setItem(logReadStorageKey(), JSON.stringify(marker));
  return marker;
}

function unreadLogSeverity(summary = {}) {
  const marker = readLogMarker();
  if (summary.latest_critical_id && summary.latest_critical_id !== marker.critical) {
    return "critical";
  }
  if (summary.latest_warning_id && summary.latest_warning_id !== marker.warning) {
    return "warning";
  }
  return "";
}

function updateLogAlert(summary = {}, { initialize = false } = {}) {
  if (!logsButton || !state.isAdmin) {
    logsButton?.classList.remove("log-alert-critical", "log-alert-warning");
    return;
  }
  if (initialize && !localStorage.getItem(logReadStorageKey())) {
    writeLogMarker(summary);
  }
  const severity = unreadLogSeverity(summary);
  logsButton.classList.toggle("log-alert-critical", severity === "critical");
  logsButton.classList.toggle("log-alert-warning", severity === "warning");
  if (severity === "critical") {
    logsButton.title = "Nowy krytyczny blad w logach.";
  } else if (severity === "warning") {
    logsButton.title = "Nowe ostrzezenie w logach.";
  } else {
    logsButton.title = "";
  }
}

function markLogsRead(payload = {}) {
  writeLogMarker(payload.summary || {});
  updateLogAlert(payload.summary || {});
}

function logSeverityLabel(severity = "info") {
  if (severity === "critical") return "Krytyczny";
  if (severity === "warning") return "Ostrzezenie";
  return "Info";
}

function renderLogEvent(event) {
  const block = document.createElement("article");
  const meta = document.createElement("div");
  const title = document.createElement("strong");
  const source = document.createElement("span");
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const lines = document.createElement("pre");
  const severity = event.severity || "info";
  block.className = `log-event log-event-${severity}`;
  meta.className = "log-event-meta";
  meta.textContent = [event.time || "", logSeverityLabel(severity)].filter(Boolean).join(" | ");
  title.textContent = event.summary || "Zdarzenie";
  source.textContent = event.path || "";
  summary.textContent = "Szczegoly";
  lines.className = "log-lines";
  lines.textContent = (event.lines || []).join("\n");
  details.append(summary, lines);
  block.append(meta, title, source, details);
  return block;
}

function renderLogs(payload) {
  state.logs = payload;
  logsOutput.textContent = "";
  const logs = payload.logs || [];
  const hasEvents = logs.some((log) => (log.events || []).length);
  if (!hasEvents) {
    logsOutput.className = "logs-output empty-state";
    logsOutput.textContent = "Brak zdarzen w logach systemowych.";
    return;
  }
  logsOutput.className = "logs-output";
  for (const log of logs) {
    const category = document.createElement("section");
    const heading = document.createElement("div");
    const title = document.createElement("strong");
    const path = document.createElement("span");
    const events = log.events || [];
    category.className = "log-category";
    heading.className = "log-category-heading";
    title.textContent = `${log.label || log.key || "Log"} (${events.length})`;
    path.textContent = log.path || "";
    heading.append(title, path);
    category.appendChild(heading);
    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "Brak zdarzen w tej kategorii.";
      category.appendChild(empty);
    } else {
      for (const event of events) {
        category.appendChild(renderLogEvent(event));
      }
    }
    logsOutput.appendChild(category);
  }
}

async function loadLogs({ markRead = true } = {}) {
  const payload = await requestJson("/api/logs?limit=400");
  updateLogAlert(payload.summary || {});
  renderLogs(payload);
  if (markRead) {
    markLogsRead(payload);
  }
}

async function pollLogStatus({ initialize = false } = {}) {
  if (!state.isAdmin) {
    updateLogAlert({});
    return;
  }
  const payload = await requestJson("/api/logs?limit=120");
  updateLogAlert(payload.summary || {}, { initialize });
}

function createPoller(name, intervalMs, callback, options = {}) {
  const maxDelayMs = Number(options.maxDelayMs || 60000);
  const hiddenDelayMs = Number(options.hiddenDelayMs || POLL_HIDDEN_DELAY_MS);
  const poller = {
    name,
    intervalMs,
    failures: 0,
    timer: 0,
    running: false,
  };
  const schedule = (delayMs = intervalMs) => {
    if (poller.timer) {
      window.clearTimeout(poller.timer);
    }
    poller.timer = window.setTimeout(run, Math.max(0, delayMs));
  };
  const nextDelay = () => {
    if (document.hidden) {
      return hiddenDelayMs;
    }
    if (!poller.failures) {
      return intervalMs;
    }
    return Math.min(maxDelayMs, intervalMs * 2 ** poller.failures);
  };
  const run = async () => {
    poller.timer = 0;
    if (document.hidden) {
      schedule(hiddenDelayMs);
      return;
    }
    if (poller.running) {
      schedule(intervalMs);
      return;
    }
    poller.running = true;
    try {
      await callback();
      poller.failures = 0;
    } catch (_error) {
      poller.failures += 1;
    } finally {
      poller.running = false;
      schedule(nextDelay());
    }
  };
  poller.schedule = schedule;
  poller.kick = () => {
    schedule(0);
  };
  state.pollers.push(poller);
  return poller;
}

function startBackgroundPollers() {
  createPoller("fileIndex", 5000, refreshFileIndexStatus).schedule(5000);
  createPoller("logs", 15000, pollLogStatus).schedule(15000);
  createPoller("processQueue", 2500, refreshProcessQueue).schedule(2500);
  createPoller("activeUsers", 15000, refreshActiveUsersPresence).schedule(15000);
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    return;
  }
  state.pollers.forEach((poller) => poller.kick());
  if ([...state.processJobs.values()].some(processJobIsActive)) {
    scheduleProcessJobPoll(0);
  }
});

function openLogsClearModal() {
  if (!logsClearPassword || !logsClearStatus) {
    return;
  }
  logsClearStatus.textContent = "";
  logsClearPassword.value = "";
  document.querySelector("#logsClearModal")?.classList.add("active");
  window.setTimeout(() => logsClearPassword?.focus(), 0);
}

function closeLogsClearModal() {
  if (!logsClearPassword || !logsClearStatus) {
    return;
  }
  logsClearPassword.value = "";
  logsClearStatus.textContent = "";
  document.querySelector("#logsClearModal")?.classList.remove("active");
}

async function clearLogs(password) {
  if (!password) {
    return;
  }
  if (logsClearStatus) {
    logsClearStatus.textContent = "Czyszczenie...";
  }
  const payload = await requestJson("/api/logs/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  renderLogs(payload);
  markLogsRead(payload);
  if ((payload.clear_errors || []).length) {
    if (logsClearStatus) {
      logsClearStatus.textContent = `Nie wyczyszczono wszystkich logow: ${(payload.clear_errors || []).join(
        "; "
      )}`;
    }
    return;
  }
  closeLogsClearModal();
}

function formPayload() {
  return {
    product_id: productForm.elements.product_id.value,
    name: productForm.elements.name.value,
    type_name: productForm.elements.type_name.value,
    model: productForm.elements.model.value,
    color1: productForm.elements.color1.value,
    color2: productForm.elements.color2.value,
    color3: productForm.elements.color3.value,
    extra: productForm.elements.extra.value,
    ean: productForm.elements.ean.value,
  };
}

function normalizedIdentityValue(value) {
  return String(value || "").trim().toUpperCase();
}

function productEntryLabel(entry = {}) {
  const colors = [entry.color1, entry.color2, entry.color3].filter(Boolean).join(" / ");
  const parts = [entry.name, entry.type_name, entry.model, colors, entry.extra].filter(Boolean);
  const suffix = entry.ean ? `EAN ${entry.ean}` : entry.product_id || "";
  return parts.join(" | ") + (suffix ? ` - ${suffix}` : "");
}

function entryFromProcessPayload(payload = {}, fallback = {}) {
  const result = payload.entry || {};
  const raw = result.entry || {};
  const entry = {
    product_id: result.product_id || raw.PRODUCT_ID || fallback.product_id || "",
    ean: raw.EAN || fallback.ean || payload.ean || "",
    name: raw.NAZWA || fallback.name || "",
    type_name: raw.TYP || fallback.type_name || "",
    model: raw.MODEL || fallback.model || "",
    color1: raw.KOLOR1 || fallback.color1 || "",
    color2: raw.KOLOR2 || fallback.color2 || "",
    color3: raw.KOLOR3 || fallback.color3 || "",
    extra: raw.DODATKI || fallback.extra || "",
  };
  entry.label = productEntryLabel(entry);
  return entry;
}

function upsertProductEntry(entry = {}) {
  if (!entry.product_id && !entry.ean) return;
  const productId = normalizedIdentityValue(entry.product_id);
  const ean = normalizedIdentityValue(entry.ean);
  const entries = [...(state.entries || [])];
  const index = entries.findIndex((item) => {
    const itemProductId = normalizedIdentityValue(item.product_id);
    const itemEan = normalizedIdentityValue(item.ean);
    return (productId && itemProductId === productId) || (ean && itemEan === ean);
  });
  if (index >= 0) {
    entries[index] = { ...entries[index], ...entry, label: entry.label || entries[index].label };
  } else {
    entries.unshift(entry);
  }
  state.entries = entries;
  renderEntrySelect();
}

function productFieldsChangedSinceLoad() {
  if (!state.loadedEntryOriginal) {
    return false;
  }
  const current = formPayload();
  return trackedProductFields.some(
    (fieldName) =>
      normalizedIdentityValue(current[fieldName]) !==
      normalizedIdentityValue(state.loadedEntryOriginal[fieldName])
  );
}

function hasProductDraftData() {
  const current = formPayload();
  return trackedProductFields.some((fieldName) => String(current[fieldName] || "").trim());
}

function hasPendingSlotChanges() {
  if (state.files.size || state.deletedSlots.size) {
    return true;
  }
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    if (photo?.dirty) {
      return true;
    }
  }
  return false;
}

function slotHasPendingUserEdit(prefix) {
  return Boolean(
    state.files.has(prefix) ||
      state.deletedSlots.has(prefix) ||
      state.loadedPhotos.get(prefix)?.dirty
  );
}

function pendingChangedSlotPrefixes() {
  const prefixes = new Set();
  for (const prefix of state.files.keys()) prefixes.add(prefix);
  for (const prefix of state.deletedSlots.keys()) prefixes.add(prefix);
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    if (photo?.dirty) {
      prefixes.add(prefix);
    }
  }
  return prefixes;
}

function clearSavedSlotMarkers(prefixes) {
  for (const prefix of prefixes || []) {
    const photo = state.loadedPhotos.get(prefix);
    if (photo?.dirty) {
      const clean = { ...photo };
      delete clean.dirty;
      state.loadedPhotos.set(prefix, clean);
    }
    state.deletedSlots.delete(prefix);
    state.files.delete(prefix);
    state.userSelectedSlotSources.delete(prefix);
  }
}

function hasPendingUserChanges() {
  return (
    hasPendingSlotChanges() ||
    productFieldsChangedSinceLoad() ||
    (!state.loadedEntryOriginal && hasProductDraftData())
  );
}

function updateSubmitButtonState() {
  if (!submitButton || submitButton.dataset.busy === "1") {
    return;
  }
  const pendingUploads = activeSlotUploads();
  if (pendingUploads.length) {
    submitButton.disabled = true;
    submitButton.textContent = `Wysylanie ${pendingUploads.length}`;
    submitButton.title = "Poczekaj, az nowe pliki trafia do cache backendu.";
    submitButton.setAttribute("aria-label", submitButton.textContent);
    return;
  }
  const failedUploads = failedSlotUploads();
  if (failedUploads.length) {
    const [prefix, item] = failedUploads[0];
    const reason = slotUploadError(item);
    submitButton.disabled = true;
    submitButton.textContent = "Upload nieudany";
    submitButton.title = reason
      ? `Slot ${prefix}: ${reason}`
      : "Popraw slot z nieudanym uploadem albo wybierz plik ponownie.";
    submitButton.setAttribute(
      "aria-label",
      reason ? `Upload nieudany: slot ${prefix}: ${reason}` : submitButton.textContent
    );
    return;
  }
  submitButton.disabled = false;
  const hasChanges = hasPendingUserChanges();
  submitButton.textContent = hasChanges ? "Aktualizuj" : "Synchronizuj";
  submitButton.title = hasChanges
    ? "Zapisuje zmiany w danych i slotach oraz aktualizuje lokalne pliki, FTP i SQL."
    : "Pobiera brakujace zdjecia z FTP i uzupelnia lokalne pliki.";
  submitButton.setAttribute("aria-label", submitButton.textContent);
}

function pageExitWarningText() {
  const reasons = [];
  if (hasPendingUserChanges()) reasons.push("sa niezapisane zmiany");
  if (activeSlotUploads().length) reasons.push("trwa wysylanie plikow");
  if (state.photosLoading) reasons.push("trwa wczytywanie danych");
  if (submitButton?.dataset.busy === "1") reasons.push("trwa zapisywanie");
  const detail = reasons.length ? ` (${reasons.join(", ")})` : "";
  return `Opuscic strone${detail}?`;
}

function shouldConfirmPageExit() {
  if (state.navigationGuardBypass) return false;
  return Boolean(
    hasPendingUserChanges() ||
      activeSlotUploads().length ||
      state.photosLoading ||
      submitButton?.dataset.busy === "1"
  );
}

function confirmPageExit() {
  if (!shouldConfirmPageExit()) return true;
  return window.confirm(pageExitWarningText());
}

function continueBrowserBackNavigation() {
  state.navigationGuardBypass = true;
  window.history.back();
  window.setTimeout(() => {
    state.navigationGuardBypass = false;
    if (!window.history.state?.picorgLeaveGuard) {
      window.history.pushState({ picorgLeaveGuard: true }, "", window.location.href);
    }
  }, 600);
}

function setupPageExitGuards() {
  window.addEventListener("pagehide", () => {
    notifyActiveUsersPresenceLeave();
  });
  window.addEventListener("beforeunload", (event) => {
    if (!shouldConfirmPageExit()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  if (!window.history?.pushState) {
    return;
  }
  window.history.replaceState({ ...(window.history.state || {}), picorgBase: true }, "", window.location.href);
  window.history.pushState({ picorgLeaveGuard: true }, "", window.location.href);
  window.addEventListener("popstate", () => {
    if (state.navigationGuardBypass) return;
    if (!confirmPageExit()) {
      window.history.pushState({ picorgLeaveGuard: true }, "", window.location.href);
      return;
    }
    continueBrowserBackNavigation();
  });
}

function mergePhotoRecord(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming };
  for (const key of ["local", "ftp", "sql", "is_image", "sql_checked"]) {
    merged[key] = Boolean(existing[key] || incoming[key]);
  }
  for (const key of [
    "filename",
    "path",
    "token",
    "url",
    "thumb_url",
    "file_version",
    "ftp_filename",
    "ftp_path",
    "ftp_token",
    "ftp_url",
    "ftp_thumb_url",
    "ftp_file_version",
    "sql_value",
  ]) {
    if (incoming[key]) {
      merged[key] = incoming[key];
    } else if (existing[key]) {
      merged[key] = existing[key];
    } else {
      merged[key] = "";
    }
  }
  if (incoming.sql_checked) {
    merged.sql = Boolean(incoming.sql);
    merged.sql_checked = true;
    merged.sql_value = incoming.sql_value || "";
  }
  merged.prefix = incoming.prefix || existing.prefix || "";
  const cachedFtp = state.ftpPreviewCache.get(
    ftpPreviewCacheKey(merged, formValue("ean") || state.loadedEntryOriginal?.ean || "")
  );
  if (cachedFtp) {
    return applyCachedFtpPreview(merged, merged.prefix, cachedFtp);
  }
  return merged;
}

function photoLoadingText() {
  const loading = [];
  for (const [source, status] of state.photoSourceStatus.entries()) {
    if (status === "pending" || status === "loading") {
      loading.push(photoSourceLabels[source] || source);
    }
  }
  return loading.length ? `Wczytywanie: ${loading.join(", ")}` : "Wczytywanie";
}

function photoStatusSummary() {
  const done = [];
  const loading = [];
  const failed = [];
  for (const [source, status] of state.photoSourceStatus.entries()) {
    if (status === "done") done.push(photoSourceLabels[source] || source);
    if (status === "pending" || status === "loading") loading.push(photoSourceLabels[source] || source);
    if (status === "failed") failed.push(photoSourceLabels[source] || source);
  }
  const parts = [];
  if (done.length) parts.push(`gotowe: ${done.join(", ")}`);
  if (loading.length) parts.push(`trwa: ${loading.join(", ")}`);
  if (failed.length) parts.push(`blad: ${failed.join(", ")}`);
  return parts.join(" | ");
}

function setPhotoSourceStatus(source, status, requestId) {
  if (requestId !== state.photoLoadRequestId) return;
  state.photoSourceStatus.set(source, status);
  const summary = photoStatusSummary();
  formStatus.textContent = summary || photoLoadingText();
}

function applyPhotoPayload(photos = [], options = {}) {
  const changedPrefixes = new Set();
  const allowedPrefixes = options.prefixes instanceof Set ? options.prefixes : null;
  for (const photo of photos) {
    if (!photo?.prefix) continue;
    if (allowedPrefixes && !allowedPrefixes.has(photo.prefix)) continue;
    if (!options.force && state.files.has(photo.prefix)) {
      const existing = state.loadedPhotos.get(photo.prefix) || {};
      const merged = mergePhotoRecord(existing, photo);
      state.loadedPhotos.set(photo.prefix, merged);
      applyDefaultSlotSource(photo.prefix, merged);
      if (photoHasUsableContent(photo)) {
        for (const changedPrefix of relocateProvisionalSlotFile(photo.prefix)) {
          changedPrefixes.add(changedPrefix);
        }
      }
      continue;
    }
    if (!options.force && slotHasPendingUserEdit(photo.prefix)) continue;
    const existing = state.loadedPhotos.get(photo.prefix) || {};
    const merged = mergePhotoRecord(existing, photo);
    if (options.clearDirty) {
      delete merged.dirty;
    }
    state.loadedPhotos.set(photo.prefix, merged);
    applyDefaultSlotSource(photo.prefix, merged);
    changedPrefixes.add(photo.prefix);
  }
  if (changedPrefixes.size) {
    renderChangedSlots(changedPrefixes);
    scheduleBackgroundFtpPreviewLoad(undefined, 1500);
  }
  return changedPrefixes;
}

function photoRequestTimeoutMs(source) {
  if (source === "ftp") return 15000;
  if (source === "all") return 25000;
  return 20000;
}

async function requestEntryPhotos(entry, source, prefixes = null, options = {}) {
  const params = new URLSearchParams({ source });
  if (prefixes && prefixes.size) {
    params.set("prefixes", [...prefixes].join(","));
  }
  return requestJson(`/api/entries/photos?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
    timeoutMs: Number(options.timeoutMs || photoRequestTimeoutMs(source)),
  });
}

function backgroundFtpLookupKey(fields = formPayload()) {
  const ean = normalizedIdentityValue(fields.ean);
  if (!state.ftpEnabled || !/^\d{13}$/.test(ean)) return "";
  for (const fieldName of ["name", "type_name", "model", "color1"]) {
    if (!String(fields[fieldName] || "").trim()) return "";
  }
  return [
    ean,
    normalizedIdentityValue(fields.name),
    normalizedIdentityValue(fields.type_name),
    normalizedIdentityValue(fields.model),
    normalizedIdentityValue(fields.color1),
    normalizedIdentityValue(fields.color2),
    normalizedIdentityValue(fields.color3),
    normalizedIdentityValue(fields.extra),
  ].join("|");
}

function clearStaleBackgroundFtpPhotos(activeKey) {
  let changed = false;
  for (const [prefix, photo] of Array.from(state.loadedPhotos.entries())) {
    if (!photo?.background_ftp_key || photo.background_ftp_key === activeKey) continue;
    if (slotHasPendingUserEdit(prefix)) continue;
    state.loadedPhotos.delete(prefix);
    state.slotSources.delete(prefix);
    state.userSelectedSlotSources.delete(prefix);
    changed = true;
    renderSlot(prefix);
  }
  if (changed) updateSubmitButtonState();
}

async function loadBackgroundFtpPhotosForCurrentForm() {
  const entry = formPayload();
  const key = backgroundFtpLookupKey(entry);
  if (!key) {
    state.backgroundFtpLookupKey = "";
    clearStaleBackgroundFtpPhotos("");
    return;
  }
  clearStaleBackgroundFtpPhotos(key);
  if (state.backgroundFtpLookupKey === key) return;
  state.backgroundFtpLookupKey = key;
  const requestId = state.backgroundFtpLookupRequestId + 1;
  state.backgroundFtpLookupRequestId = requestId;
  try {
    const payload = await requestEntryPhotos(entry, "ftp", null, { timeoutMs: 15000 });
    if (state.backgroundFtpLookupRequestId !== requestId) return;
    if (backgroundFtpLookupKey() !== key) return;
    const photos = (payload.photos || []).map((photo) => ({
      ...photo,
      background_ftp_key: key,
    }));
    applyPhotoPayload(photos, { force: false });
    if (photos.length) {
      formStatus.textContent = `Znaleziono zdjecia FTP: ${photos.length}.`;
    }
    updateSubmitButtonState();
  } catch (error) {
    if (state.backgroundFtpLookupRequestId === requestId && showTimingDetails()) {
      formStatus.textContent = `Nie udalo sie sprawdzic FTP w tle: ${error.message}`;
    }
  }
}

function scheduleBackgroundFtpLookup(delay = 900) {
  window.clearTimeout(state.backgroundFtpLookupTimer);
  state.backgroundFtpLookupTimer = window.setTimeout(() => {
    loadBackgroundFtpPhotosForCurrentForm().catch(() => {});
  }, delay);
}

function clearSelectedFiles() {
  for (const prefix of Array.from(state.filePreviewUrls.keys())) {
    revokeFilePreviewUrl(prefix);
  }
  state.files.clear();
}

async function loadPhotosForEntry(entry, options = {}) {
  const started = performance.now();
  const progressive = options.progressive !== false;
  const targetPrefixes = new Set((options.prefixes || []).map((prefix) => String(prefix || "").trim()).filter(Boolean));
  const partial = targetPrefixes.size > 0;
  const requestId = state.photoLoadRequestId + 1;
  state.photoLoadRequestId = requestId;
  state.photosLoading = true;
  const collectedPrefixes = new Set();
  if (!partial) {
    state.loadedPhotos.clear();
    state.deletedSlots.clear();
    state.slotSources.clear();
    state.userSelectedSlotSources.clear();
    state.ftpPreviewLoading.clear();
    state.ftpPreviewBackgroundLoading.clear();
    state.photoSourcesLoaded.clear();
    state.backgroundFtpLookupKey = "";
    state.backgroundFtpLookupRequestId += 1;
    window.clearTimeout(state.backgroundFtpLookupTimer);
  } else {
    for (const prefix of targetPrefixes) {
      state.ftpPreviewLoading.delete(prefix);
      state.ftpPreviewBackgroundLoading.delete(prefix);
      state.userSelectedSlotSources.delete(prefix);
    }
  }
  window.clearTimeout(state.backgroundFtpPreviewTimer);
  const sources = progressive ? ["local", "sql", "ftp"] : ["all"];
  state.photoSourceStatus.clear();
  for (const source of sources) {
    state.photoSourceStatus.set(source, "pending");
  }
  formStatus.textContent = photoLoadingText();
  if (!partial) {
    renderSlotsExceptPendingUserEdits();
  }
  const tasks = sources.map(async (source) => {
    setPhotoSourceStatus(source, "loading", requestId);
    try {
      const payload = await requestEntryPhotos(entry, source, partial ? targetPrefixes : null);
      if (state.photoLoadRequestId === requestId) {
        setPhotoSourceStatus(source, "done", requestId);
        state.photoSourcesLoaded.add(payload.source || source);
        const payloadPhotos = partial
          ? (payload.photos || []).filter((photo) => targetPrefixes.has(photo?.prefix))
          : payload.photos || [];
        for (const photo of payloadPhotos) {
          if (photo?.prefix) collectedPrefixes.add(photo.prefix);
        }
        applyPhotoPayload(payloadPhotos, {
          prefixes: partial ? targetPrefixes : null,
          force: Boolean(options.force),
          clearDirty: Boolean(options.clearDirty),
        });
        if ((payload.source || source) === "ftp" || (payload.source || source) === "all") {
          scheduleBackgroundFtpPreviewLoad(requestId, 1200);
        }
        updateSubmitButtonState();
      }
      return payload;
    } catch (error) {
      setPhotoSourceStatus(source, "failed", requestId);
      throw error;
    }
  });
  try {
    const settled = await Promise.allSettled(tasks);
    if (state.photoLoadRequestId !== requestId) return;
    const failures = settled.filter((item) => item.status === "rejected");
    if (failures.length && failures.length === settled.length) {
      throw failures[0].reason;
    }
    if (failures.length) {
      formStatus.textContent = "Czesc zrodel podgladu nie odpowiedziala.";
    } else {
      formStatus.textContent = photoStatusSummary() || "Wczytano podglady.";
    }
    state.lastLookupMs = performance.now() - started;
  } finally {
    if (state.photoLoadRequestId !== requestId) return;
    state.photosLoading = false;
    state.photoSourceStatus.clear();
    if (partial) {
      for (const prefix of targetPrefixes) {
        if (!collectedPrefixes.has(prefix) && !slotHasPendingUserEdit(prefix)) {
          state.loadedPhotos.delete(prefix);
          state.slotSources.delete(prefix);
          state.userSelectedSlotSources.delete(prefix);
          state.slotFits.delete(prefix);
          bumpSlotRevision(prefix);
        }
      }
    }
    updateRuntimeMetrics();
    renderSlotsExceptPendingUserEdits(partial ? targetPrefixes : null);
    scheduleBackgroundFtpPreviewLoad(requestId, 1500);
  }
}

function fillForm(entry, options = {}) {
  state.suppressAutoSearch = true;
  state.loadedEntryOriginal = { ...entry };
  state.slotFits.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  state.userSelectedSlotSources.clear();
  state.ftpPreviewLoading.clear();
  state.ftpPreviewBackgroundLoading.clear();
  state.photoSourcesLoaded.clear();
  state.backgroundFtpLookupKey = "";
  state.backgroundFtpLookupRequestId += 1;
  window.clearTimeout(state.backgroundFtpLookupTimer);
  productForm.elements.product_id.value = entry.product_id || "";
  productForm.elements.name.value = entry.name || "";
  productForm.elements.type_name.value = entry.type_name || "";
  productForm.elements.model.value = entry.model || "";
  productForm.elements.color1.value = entry.color1 || "";
  productForm.elements.color2.value = entry.color2 || "";
  productForm.elements.color3.value = entry.color3 || "";
  productForm.elements.extra.value = entry.extra || "";
  productForm.elements.ean.value = entry.ean || "";
  handlePimcoreEanInput();
  applyProductFieldSettings();
  formStatus.textContent = entry.product_id ? `Wczytano ${entry.product_id}` : "Wczytano wpis";
  updateFieldWarnings();
  setTimeout(() => {
    state.suppressAutoSearch = false;
  }, 200);
  if (options.loadPhotos) {
    loadPhotosForEntry({ ...entry, ...formPayload() }).catch((error) => {
      formStatus.textContent = `Wpis wczytany, ale zdjecia nie: ${error.message}`;
    });
  }
}

async function refreshData() {
  const payload = await requestJson("/api/data");
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  state.fileIndex = payload.file_index || state.fileIndex;
  state.ftpEnabled = payload.ftp_enabled !== false;
  state.productFields = payload.product_fields || state.productFields || {};
  renderDatalists();
  applyProductFieldLabels();
  renderEntrySelect();
  renderListEditor();
  updateRuntimeMetrics();
}

async function loadBootstrap(options = {}) {
  const payload = await requestJson("/api/bootstrap", options);
  state.csrfToken = payload.csrf_token || state.csrfToken || "";
  state.defaultSlotFit = Boolean(payload.auto_content_fit);
  state.processing = payload.processing || state.processing || {};
  state.security = payload.security || state.security || {};
  state.ftpEnabled = payload.ftp_enabled !== false;
  if (versionInfo) {
    versionInfo.textContent = payload.version ? `Wersja ${payload.version}` : "";
  }
  serverInfo.textContent = payload.processed_dir;
  logoutButton.hidden = !payload.auth_enabled;
  state.currentUser = payload.current_user || null;
  applyPimcoreRuntimeCapabilities(payload.pimcore);
  updateAdminUi();
  refreshActiveUsersPresence().catch(() => {
    renderActiveUsersPresence({ enabled: false, users: [] });
  });
  applyTimingDetailsVisibility();
  pollLogStatus({ initialize: true }).catch(() => {});
  loadRecentProcessJobs().catch(() => {});
  refreshProcessQueue().catch(() => {});
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  state.fileIndex = payload.file_index || null;
  state.ftpEnabled = payload.ftp_enabled !== false;
  state.productFields = payload.product_fields || {};
  state.processing = payload.processing || state.processing || {};
  state.security = payload.security || state.security || {};
  renderDatalists();
  applyProductFieldLabels();
  renderEntrySelect();
  renderSlots(payload.slots || []);
  renderListEditor();
  updateRuntimeMetrics();
}

async function refreshFileIndexStatus() {
  const payload = await requestJson("/api/file-index/status");
  state.fileIndex = payload;
  updateRuntimeMetrics();
}

async function searchByEan() {
  const ean = productForm.elements.ean.value.trim();
  if (!ean) {
    formStatus.textContent = "Wpisz EAN do wyszukania.";
    return;
  }
  const payload = await requestJson(`/api/entries/search?ean=${encodeURIComponent(ean)}`);
  renderEntrySelect(payload.entries || []);
  if (payload.entries && payload.entries.length === 1) {
    fillForm(payload.entries[0], { loadPhotos: true });
  } else {
    renderEntryModal(payload.entries || []);
    formStatus.textContent = `${(payload.entries || []).length} dopasowan po EAN.`;
  }
}

async function searchByProduct({ automatic = false } = {}) {
  const fields = formPayload();
  const params = new URLSearchParams({
    name: fields.name,
    type_name: fields.type_name,
    model: fields.model,
  });
  const payload = await requestJson(`/api/entries/search?${params.toString()}`);
  renderEntrySelect(payload.entries || []);
  if (payload.entries && payload.entries.length > 0) {
    renderEntryModal(payload.entries);
  }
  if (!automatic) {
    formStatus.textContent = `${(payload.entries || []).length} dopasowan produktu.`;
  }
}

let autoSearchTimer = null;
function scheduleProductAutoSearch() {
  if (state.suppressAutoSearch) {
    return;
  }
  clearTimeout(autoSearchTimer);
  autoSearchTimer = setTimeout(() => {
    const fields = formPayload();
    const key = `${fields.name}|${fields.type_name}|${fields.model}`.toUpperCase();
    if (!fields.name || !fields.type_name || !fields.model || key === state.lastAutoSearchKey) {
      return;
    }
    state.lastAutoSearchKey = key;
    searchByProduct({ automatic: true }).catch(() => {});
  }, 500);
}

async function addListValue(event) {
  event.preventDefault();
  const value = listAddInput.value.trim();
  if (!value) {
    listStatus.textContent = "Wpisz wartosc.";
    return;
  }
  const exists = (state.lists[state.selectedList] || []).some(
    (item) => normalizeListValue(item) === normalizeListValue(value)
  );
  if (exists) {
    listStatus.textContent = "Taka wartosc juz istnieje na liscie.";
    state.listFilter = value;
    renderListEditor();
    return;
  }
  const payload = await requestJson(`/api/lists/${state.selectedList}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
  state.listFilter = "";
  renderDatalists();
  renderListEditor();
  listStatus.textContent = "Dodano.";
}

async function removeListValue(value) {
  const listLabel = listLabels[state.selectedList] || state.selectedList;
  if (!window.confirm(`Usunac "${value}" z listy ${listLabel}?`)) {
    return;
  }
  let payload;
  try {
    payload = await requestJson(`/api/lists/${state.selectedList}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
  } catch (error) {
    const detail = error.detail || {};
    if (error.status === 409 && Array.isArray(detail.used_by)) {
      renderListUsageModal(detail.value || value, detail.used_by);
      listStatus.textContent = error.message;
      return;
    }
    throw error;
  }
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
  renderDatalists();
  renderListEditor();
  listStatus.textContent = "Usunieto.";
}

function inputField(name, label, value = "", attrs = {}) {
  const wrapper = document.createElement("label");
  const input = document.createElement(attrs.textarea ? "textarea" : "input");
  wrapper.textContent = label;
  input.name = name;
  if (attrs.type) input.type = attrs.type;
  if (attrs.className) wrapper.className = attrs.className;
  if (attrs.min !== undefined) input.min = attrs.min;
  if (attrs.max !== undefined) input.max = attrs.max;
  if (attrs.step !== undefined) input.step = attrs.step;
  if (attrs.placeholder !== undefined) input.placeholder = attrs.placeholder;
  if (attrs.checked !== undefined) input.checked = Boolean(attrs.checked);
  if (attrs.type === "checkbox") {
    input.value = "1";
  } else {
    input.value = value || "";
  }
  wrapper.appendChild(input);
  if (attrs.description) {
    const small = document.createElement("small");
    small.textContent = attrs.description;
    wrapper.appendChild(small);
  }
  return wrapper;
}

function checkField(name, label, checked = false, description = "") {
  const wrapper = document.createElement("div");
  const input = document.createElement("input");
  const text = document.createElement("div");
  const title = document.createElement("strong");
  wrapper.className = "check-row";
  input.type = "checkbox";
  input.name = name;
  input.checked = Boolean(checked);
  input.setAttribute("aria-label", label);
  title.textContent = label;
  text.appendChild(title);
  if (description) {
    const small = document.createElement("small");
    small.textContent = description;
    text.appendChild(small);
  }
  wrapper.append(input, text);
  return wrapper;
}

function settingsFieldGroup(titleText, ...nodes) {
  const group = document.createElement("div");
  const title = document.createElement("h2");
  group.className = "settings-field-group";
  title.textContent = titleText;
  group.appendChild(title);
  for (const node of nodes.flat()) {
    if (node) group.appendChild(node);
  }
  return group;
}

function productFieldSettingsList(settings = {}) {
  const list = document.createElement("div");
  list.className = "product-field-settings-list wide-field";
  const normalized = normalizedProductFields(settings);
  for (const [key, definition] of Object.entries(productFieldDefinitions)) {
    const item = normalized[key];
    const row = document.createElement("div");
    const title = document.createElement("strong");
    const labelField = inputField(
      `product_field_${key}_label`,
      "Wlasna nazwa",
      item.label,
      { placeholder: definition.label }
    );
    const enabled = checkField(`product_field_${key}_enabled`, "Aktywne", item.enabled);
    const required = checkField(`product_field_${key}_required`, "Wymagane", item.required);
    const enabledInput = enabled.querySelector("input");
    const requiredInput = required.querySelector("input");
    row.className = "product-field-settings-row";
    row.dataset.productFieldSetting = key;
    title.textContent = definition.label;
    const syncRequired = () => {
      requiredInput.disabled = !enabledInput.checked;
      if (!enabledInput.checked) requiredInput.checked = false;
    };
    enabledInput.addEventListener("change", syncRequired);
    syncRequired();
    row.append(title, labelField, enabled, required);
    list.appendChild(row);
  }
  return list;
}

function collectProductFieldSettings(data) {
  return Object.fromEntries(
    Object.keys(productFieldDefinitions).map((key) => [
      key,
      {
        label: data.get(`product_field_${key}_label`) || "",
        enabled: data.has(`product_field_${key}_enabled`),
        required: data.has(`product_field_${key}_required`),
      },
    ])
  );
}

function credentialField(name, label, isSet = false, attrs = {}) {
  const field = document.createElement("label");
  const title = document.createElement("span");
  const row = document.createElement("span");
  const input = document.createElement("input");
  const originalType = attrs.type || "text";
  field.className = attrs.className ? `credential-field ${attrs.className}` : "credential-field";
  title.textContent = label;
  row.className = "credential-actions";
  input.name = name;
  input.type = originalType;
  input.placeholder = isSet ? "Zapisane - wpisz nowe, zeby zmienic" : "Nie ustawiono";
  row.appendChild(input);
  if (attrs.secretPath && isSet) {
    const reveal = document.createElement("button");
    reveal.type = "button";
    reveal.className = "secondary-button";
    reveal.textContent = "Pokaz zapisane";
    reveal.title = "Wymaga hasla administratora i pokazuje wartosc tylko tymczasowo.";
    reveal.addEventListener("click", () => {
      toggleCredentialReveal(input, reveal, attrs.secretPath, originalType);
    });
    row.appendChild(reveal);
  }
  field.append(title, row);
  return field;
}

function secretValueByPath(payload, path) {
  let value = payload;
  for (const part of String(path || "").split(".")) {
    if (!part) continue;
    value = value?.[part];
  }
  return value === undefined || value === null ? "" : String(value);
}

const secretRevealTimers = new WeakMap();

function clearSecretRevealTimer(input) {
  const timer = secretRevealTimers.get(input);
  if (timer) {
    window.clearTimeout(timer);
    secretRevealTimers.delete(input);
  }
}

function hideCredentialSecret(input, button, originalType) {
  clearSecretRevealTimer(input);
  input.value = "";
  input.type = originalType;
  input.dataset.secretVisible = "";
  button.textContent = "Pokaz zapisane";
}

async function loadSettingsSecrets(password) {
  return requestJson("/api/settings/secrets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
    timeoutMs: 10000,
  });
}

let secretRevealResolve = null;

function closeSecretRevealModal(result = null) {
  if (secretRevealModal) {
    secretRevealModal.classList.remove("active");
  }
  if (secretRevealPassword) {
    secretRevealPassword.value = "";
  }
  if (secretRevealStatus) {
    secretRevealStatus.textContent = "";
  }
  if (secretRevealResolve) {
    const resolve = secretRevealResolve;
    secretRevealResolve = null;
    resolve(result);
  }
}

function requestSecretRevealPassword() {
  if (!secretRevealModal || !secretRevealPassword || !secretRevealStatus) {
    return Promise.reject(new Error("Brak formularza potwierdzenia hasla administratora."));
  }
  if (secretRevealResolve) {
    closeSecretRevealModal();
  }
  secretRevealPassword.value = "";
  secretRevealStatus.textContent = "";
  secretRevealModal.classList.add("active");
  window.setTimeout(() => secretRevealPassword.focus(), 0);
  return new Promise((resolve) => {
    secretRevealResolve = resolve;
  });
}

async function toggleCredentialReveal(input, button, secretPath, originalType) {
  if (input.dataset.secretVisible === "1") {
    hideCredentialSecret(input, button, originalType);
    return;
  }
  const password = await requestSecretRevealPassword();
  if (password === null) {
    return;
  }
  if (!password) {
    settingsStatus.textContent = "Podaj haslo administratora.";
    return;
  }
  const previousLabel = button.textContent;
  button.disabled = true;
  button.textContent = "Wczytywanie...";
  try {
    const payload = await loadSettingsSecrets(password);
    const value = secretValueByPath(payload, secretPath);
    if (!value) {
      settingsStatus.textContent = "Brak zapisanej wartosci albo nie mozna jej odczytac aktualnym APP_SECRET.";
      button.textContent = previousLabel;
      return;
    }
    input.value = value;
    if (originalType === "password") {
      input.type = "text";
    }
    input.dataset.secretVisible = "1";
    button.textContent = "Ukryj";
    clearSecretRevealTimer(input);
    secretRevealTimers.set(
      input,
      window.setTimeout(() => hideCredentialSecret(input, button, originalType), SECRET_REVEAL_MS)
    );
    settingsStatus.textContent = "Wczytano zapisana wartosc do pola na 60 s. Zapisz tylko wtedy, gdy chcesz ja utrwalic.";
  } catch (error) {
    settingsStatus.textContent = error.message || "Nie udalo sie wczytac zapisanej wartosci.";
    button.textContent = previousLabel;
  } finally {
    state.settingsSecrets = null;
    button.disabled = false;
  }
}

function selectField(name, label, value, choices) {
  const wrapper = document.createElement("label");
  const select = document.createElement("select");
  wrapper.textContent = label;
  select.name = name;
  for (const [choiceValue, choiceLabel] of choices) {
    const option = document.createElement("option");
    option.value = choiceValue;
    option.textContent = choiceLabel;
    option.selected = choiceValue === value;
    select.appendChild(option);
  }
  wrapper.appendChild(select);
  return wrapper;
}

function actionRow(...buttons) {
  const actions = document.createElement("div");
  actions.className = "settings-actions";
  actions.append(...buttons);
  return actions;
}

function formatDiagnosticResult(target, payload) {
  if (target === "local" && Array.isArray(payload.checks)) {
    const failed = payload.checks.filter((item) => !item.read || !item.write);
    if (!failed.length) {
      return "Foldery lokalne: odczyt i zapis dzialaja.";
    }
    return failed
      .map((item) => `${item.key}: ${item.error || "brak odczytu lub zapisu"} (${item.path})`)
      .join(" | ");
  }
  return payload.message || (payload.ok ? "Test zakonczony powodzeniem." : "Test nie powiodl sie.");
}

function diagnosticButton(target, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = label;
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Testowanie...";
    try {
      const payload = await requestJson(`/api/diagnostics/${target}`, { method: "POST" });
      settingsStatus.textContent = formatDiagnosticResult(target, payload);
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function detectSqlColumnsButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Wykryj pola SQL";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Wykrywanie pol SQL...";
    try {
      const payload = await requestJson("/api/settings/sql-columns/detect", {
        method: "POST",
        timeoutMs: 60000,
      });
      if (payload.settings) {
        state.settings = payload.settings;
        state.currentUser = state.settings.current_user || state.currentUser;
      } else if (Array.isArray(payload.columns)) {
        state.settings.sql_available_columns = payload.columns;
      }
      ensureSqlColumnsDatalist();
      renderSettings();
      settingsStatus.textContent = payload.message || "Wykryto pola SQL.";
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie wykryc pol SQL.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function fileIndexRefreshButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Odswiez indeks";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Uruchamiam indeksowanie...";
    try {
      const payload = await requestJson("/api/file-index/refresh", { method: "POST" });
      state.fileIndex = payload;
      updateRuntimeMetrics();
      settingsStatus.textContent = payload.label || "Indeksowanie uruchomione.";
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function importLegacyDataButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Importuj stare dane do SQLite";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Importowanie danych legacy...";
    try {
      const payload = await requestJson("/api/settings/import-legacy", {
        method: "POST",
        timeoutMs: 120000,
      });
      if (payload.settings) {
        state.settings = payload.settings;
      }
      settingsStatus.textContent = payload.message || "Import zakonczony.";
      renderSettings();
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie zaimportowac danych.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function repairSqliteDatabaseButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Napraw SQLite";
  button.addEventListener("click", async () => {
    if (!window.confirm("Utworzyc kopie i uruchomic naprawe aktywnej bazy SQLite?")) {
      return;
    }
    button.disabled = true;
    settingsStatus.textContent = "Naprawianie SQLite...";
    try {
      const payload = await requestJson("/api/settings/sqlite/repair", {
        method: "POST",
        timeoutMs: 120000,
      });
      if (payload.settings) {
        state.settings = payload.settings;
        renderSettings();
      }
      settingsStatus.textContent = payload.message || "Naprawa SQLite zakonczona.";
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie naprawic SQLite.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function manualSqliteBackupButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Utworz kopie SQLite";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Tworzenie kopii SQLite...";
    try {
      const payload = await requestJson("/api/settings/sqlite/backup", {
        method: "POST",
        timeoutMs: 60000,
      });
      settingsStatus.textContent = `Utworzono kopie: ${payload.backup_path || "SQLite"}`;
      await loadSqliteBackups();
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie utworzyc kopii SQLite.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

async function loadSqliteBackups() {
  const payload = await requestJson("/api/settings/sqlite/backups");
  renderBackupHistory(payload.items || []);
  return payload.items || [];
}

function backupHistoryButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Historia wersji";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Wczytywanie historii kopii...";
    try {
      await loadSqliteBackups();
      document.querySelector("#backupHistoryModal")?.classList.add("active");
      settingsStatus.textContent = "Wczytano historie kopii.";
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie wczytac historii kopii.";
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function sqliteBackupScheduleGrid(settings = {}) {
  const wrapper = document.createElement("div");
  const grid = document.createElement("div");
  const selectedSlots = new Set(settings.slots || []);
  if (!selectedSlots.size) {
    const selectedDays = new Set(settings.days || []);
    const selectedHours = new Set((settings.hours || []).map((hour) => Number(hour)));
    for (const day of selectedDays) {
      for (const hour of selectedHours) {
        selectedSlots.add(`${day}:${hour}`);
      }
    }
  }
  wrapper.className = "sqlite-backup-settings wide-field";
  wrapper.appendChild(
    checkField(
      "sqlite_backup_enabled",
      "Automatyczne kopie SQLite",
      settings.enabled,
      "Backend tworzy kopie w wybrane dni i godziny."
    )
  );
  grid.className = "sqlite-backup-grid";
  const corner = document.createElement("span");
  corner.textContent = "Dzien";
  grid.appendChild(corner);
  for (let hour = 0; hour < 24; hour += 1) {
    const label = document.createElement("span");
    label.textContent = String(hour).padStart(2, "0");
    grid.appendChild(label);
  }
  for (const [key, labelText] of SQLITE_BACKUP_DAYS) {
    const day = document.createElement("strong");
    day.textContent = labelText;
    grid.appendChild(day);
    for (let hour = 0; hour < 24; hour += 1) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "sqlite_backup_slot";
      input.value = `${key}:${hour}`;
      input.checked = selectedSlots.has(input.value);
      input.setAttribute("aria-label", `Kopia ${labelText} ${String(hour).padStart(2, "0")}:00`);
      label.title = `${labelText} ${String(hour).padStart(2, "0")}:00`;
      label.appendChild(input);
      grid.appendChild(label);
    }
  }
  wrapper.appendChild(grid);
  return wrapper;
}

function collectSqliteBackupSchedule(form) {
  const data = new FormData(form);
  const slots = [...form.querySelectorAll('[name="sqlite_backup_slot"]:checked')]
    .map((input) => input.value)
    .filter(Boolean);
  const days = [...new Set(slots.map((slot) => slot.split(":")[0]).filter(Boolean))];
  const hours = [
    ...new Set(
      slots
        .map((slot) => Number(slot.split(":")[1]))
        .filter((hour) => Number.isFinite(hour))
    ),
  ].sort((a, b) => a - b);
  return {
    enabled: data.has("sqlite_backup_enabled"),
    slots,
    days,
    hours,
    max_copies: Math.max(1, Math.min(999, Number(data.get("sqlite_backup_max_copies") || 10))),
  };
}

function backupItemLabel(item) {
  const parts = [item.created_at || "bez daty"];
  if (item.reason) parts.push(item.reason);
  if (item.schema_version !== undefined && item.schema_version !== null) {
    parts.push(`schema ${item.schema_version}`);
  }
  parts.push(formatFileSize(item.size_bytes || 0));
  return parts.join(" | ");
}

function renderBackupHistory(items = []) {
  if (!backupHistoryOutput) {
    return;
  }
  backupHistoryOutput.textContent = "";
  if (!items.length) {
    backupHistoryOutput.className = "backup-history-output empty-state";
    backupHistoryOutput.textContent = "Brak kopii.";
    return;
  }
  backupHistoryOutput.className = "backup-history-output";
  for (const item of items) {
    const row = document.createElement("div");
    const details = document.createElement("div");
    const title = document.createElement("strong");
    const path = document.createElement("small");
    const actions = document.createElement("div");
    const diff = document.createElement("button");
    const restore = document.createElement("button");
    const backupPath = item.backup_path || "";
    row.className = "backup-history-row";
    title.textContent = backupItemLabel(item);
    path.textContent = backupPath;
    diff.type = "button";
    diff.className = "secondary-button";
    diff.textContent = "Porownaj";
    diff.disabled = !backupPath;
    diff.addEventListener("click", () => showSqliteBackupDiff(backupPath));
    restore.type = "button";
    restore.className = "danger-button";
    restore.textContent = "Przywroc";
    restore.disabled = !backupPath;
    restore.addEventListener("click", () => restoreSqliteBackup(backupPath));
    details.append(title, path);
    actions.className = "heading-actions";
    actions.append(diff, restore);
    row.append(details, actions);
    backupHistoryOutput.appendChild(row);
  }
}

async function restoreSqliteBackup(backupPath) {
  if (!backupPath) {
    return;
  }
  if (!window.confirm("Przywrocic aktywna baze SQLite z tej kopii? Przed przywroceniem zostanie utworzona kopia aktualnej bazy.")) {
    return;
  }
  settingsStatus.textContent = "Przywracanie kopii SQLite...";
  try {
    const payload = await requestJson("/api/settings/sqlite/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup_path: backupPath }),
      timeoutMs: 120000,
    });
    if (payload.settings) {
      state.settings = payload.settings;
      renderSettings();
    }
    await loadSqliteBackups();
    settingsStatus.textContent = `Przywrocono kopie: ${payload.restored_from || backupPath}`;
  } catch (error) {
    settingsStatus.textContent = error.message || "Nie udalo sie przywrocic kopii SQLite.";
  }
}

async function showSqliteBackupDiff(backupPath) {
  if (!backupPath || !backupDiffOutput) {
    return;
  }
  backupDiffOutput.className = "backup-diff-output empty-state";
  backupDiffOutput.textContent = "Porownywanie...";
  document.querySelector("#backupDiffModal")?.classList.add("active");
  try {
    const payload = await requestJson("/api/settings/sqlite/backup-diff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup_path: backupPath }),
      timeoutMs: 60000,
    });
    backupDiffOutput.textContent = "";
    backupDiffOutput.className = "backup-diff-output";
    for (const [table, counts] of Object.entries(payload.tables || {}).sort()) {
      const row = document.createElement("div");
      const name = document.createElement("strong");
      const values = document.createElement("span");
      row.className = "backup-diff-row";
      name.textContent = table;
      values.textContent =
        `aktywna: ${counts.active || 0}, kopia: ${counts.backup || 0}, ` +
        `dodane: ${counts.added || 0}, usuniete: ${counts.removed || 0}`;
      row.append(name, values);
      backupDiffOutput.appendChild(row);
    }
    const config = payload.config || {};
    const configRow = document.createElement("div");
    const configTitle = document.createElement("strong");
    const configValues = document.createElement("span");
    configRow.className = "backup-diff-row";
    configTitle.textContent = "Ustawienia";
    configValues.textContent =
      `dodane: ${(config.added || []).length}, usuniete: ${(config.removed || []).length}, ` +
      `zmienione: ${(config.changed || []).length}`;
    configRow.append(configTitle, configValues);
    backupDiffOutput.appendChild(configRow);
  } catch (error) {
    backupDiffOutput.className = "backup-diff-output empty-state";
    backupDiffOutput.textContent = error.message || "Nie udalo sie porownac kopii SQLite.";
  }
}

function ensureSqlColumnsDatalist() {
  let datalist = document.querySelector("#sqlColumnsList");
  if (!datalist) {
    datalist = document.createElement("datalist");
    datalist.id = "sqlColumnsList";
    document.body.appendChild(datalist);
  }
  datalist.textContent = "";
  for (const column of state.settings?.sql_available_columns || []) {
    const option = document.createElement("option");
    option.value = column;
    datalist.appendChild(option);
  }
}

function settingsSaveButton(form, buildPayload) {
  const actions = document.createElement("div");
  actions.className = "settings-actions";
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Zapisz ustawienia";
  actions.appendChild(button);
  form.appendChild(actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const previousBaseDir = state.settings?.base_dir || "";
    button.disabled = true;
    settingsStatus.textContent = "Zapisywanie...";
    try {
      state.settingsSecrets = null;
      state.settings = await requestJson("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(new FormData(form))),
        timeoutMs: 60000,
      });
      if (state.settings.session_invalidated) {
        state.currentUser = null;
        updateAdminUi();
        settingsStatus.textContent =
          state.settings.session_message || "Zapisano. Zaloguj sie ponownie.";
        window.setTimeout(() => {
          window.location.href = "/login";
        }, 1500);
        return;
      }
      state.currentUser = state.settings.current_user || state.currentUser;
      state.defaultSlotFit = Boolean(state.settings.auto_content_fit);
      state.ftpEnabled = state.settings.ftp?.enabled !== false;
      state.processing = state.settings.processing || state.processing || {};
      state.security = state.settings.security || state.security || {};
      state.productFields = state.settings.product_fields || state.productFields || {};
      refreshActiveUsersPresence().catch(() => {
        renderActiveUsersPresence({ enabled: false, users: [] });
      });
      updateAdminUi();
      if (Array.isArray(state.settings.slots)) {
        renderSlots(state.settings.slots);
      }
      applyProductFieldLabels();
      let saveMessage = "Zapisano.";
      if (previousBaseDir && state.settings.base_dir !== previousBaseDir) {
        try {
          await loadBootstrap({ timeoutMs: 60000 });
          saveMessage = `Zapisano. Aktywny katalog bazowy: ${state.settings.base_dir}`;
        } catch (error) {
          saveMessage =
            `Zapisano katalog bazowy: ${state.settings.base_dir}. ` +
            `Nie udalo sie odswiezyc danych po zapisie: ${error.message || error}`;
        }
      }
      renderSettings();
      settingsStatus.textContent = saveMessage;
    } catch (error) {
      settingsStatus.textContent = error.message || "Nie udalo sie zapisac ustawien.";
    } finally {
      button.disabled = false;
    }
  });
}

function renderSettingsApp() {
  const s = state.settings;
  const form = document.createElement("form");
  form.className = "settings-form";
  const configNote = document.createElement("p");
  configNote.className = "settings-note wide-field";
  configNote.textContent =
    `Panel webowy uzywa tej samej lokalizacji i config.json co lokalna aplikacja uruchomiona na backendzie. local_settings.json: ${
      s.local_settings_path || "nieznany"
    }`;
  const runtimeWarning = document.createElement("p");
  runtimeWarning.className = "settings-note wide-field";
  runtimeWarning.textContent = s.runtime_warning ? `Ostrzezenie runtime: ${s.runtime_warning}` : "";
  const versionNote = document.createElement("p");
  versionNote.className = "settings-note wide-field";
  versionNote.textContent = `Wersja programu: ${s.version || "dev"}`;
  const productFieldsNote = document.createElement("p");
  productFieldsNote.className = "settings-note wide-field";
  productFieldsNote.textContent =
    "Pusta nazwa zachowuje etykiete domyslna. Wylaczone pola sa pomijane przy zapisie i przetwarzaniu.";
  form.append(
    settingsFieldGroup("Runtime aplikacji",
      versionNote,
      configNote,
      runtimeWarning,
      selectField("data_mode", "Tryb danych", s.data_mode || "legacy", [
        ["legacy", "Pliki legacy"],
        ["sqlite", "SQLite"],
      ]),
      inputField("image_dir", "Lokalizacja zdjec", s.image_dir || s.base_dir, {
        placeholder: "np. C:\\PicOrgFTP-SQL albo \\\\SERWER\\Udzial\\Zdjecia",
        description:
          "Folder, w ktorym backend trzyma zdjecia i cache podgladow. " +
          "Dla uslugi Windows najlepiej uzywac pelnej sciezki lokalnej albo UNC; dyski mapowane typu Z:\\ moga nie byc widoczne.",
      }),
      selectField("database_location_mode", "Lokalizacja SQLite", s.database_location_mode || "image_dir", [
        ["image_dir", "Przy zdjeciach"],
        ["custom", "Wskazana sciezka"],
        ["exe_dir", "Przy backendzie"],
      ]),
      inputField("database_path", "Plik SQLite", s.database_path || "", {
        placeholder: "np. C:\\PicOrgFTP-SQL\\picorgftp_sql.sqlite",
        description: "Uzywane tylko dla lokalizacji: wskazana sciezka.",
      }),
      actionRow(
        importLegacyDataButton(),
        repairSqliteDatabaseButton(),
        manualSqliteBackupButton(),
        backupHistoryButton()
      )
    ),
    settingsFieldGroup("Kopie zapasowe SQLite",
      sqliteBackupScheduleGrid(s.sqlite_backup || {}),
      inputField("sqlite_backup_max_copies", "Maksymalna liczba kopii", s.sqlite_backup?.max_copies || 10, {
        type: "number",
        min: 1,
        max: 999,
      })
    ),
    settingsFieldGroup("Indeks lokalny",
      checkField(
        "local_file_index",
        "Indeks plikow lokalnych",
        s.local_file_index,
        "Backend sprawdza lokalne pliki przy wczytywaniu statusow slotow."
      ),
      actionRow(diagnosticButton("local", "Test folderow backendu"), fileIndexRefreshButton())
    ),
    settingsFieldGroup("Widok panelu",
      checkField(
        "user_show_timing_details",
        "Pokazuj blok Pomiary",
        showTimingDetails(),
        "Ustawienie tylko dla aktualnego uzytkownika. Pokazuje lub ukrywa blok Pomiary z czasami kolejki i operacji."
      )
    ),
    settingsFieldGroup("Pola produktu",
      productFieldsNote,
      productFieldSettingsList(s.product_fields || {})
    )
  );
  settingsSaveButton(form, (data) => ({
    app: {
      image_dir: data.get("image_dir"),
      data_mode: data.get("data_mode"),
      database_location_mode: data.get("database_location_mode"),
      database_path: data.get("database_path"),
      local_file_index: data.has("local_file_index"),
      product_fields: collectProductFieldSettings(data),
    },
    sqlite_backup: collectSqliteBackupSchedule(form),
  }));
  form.addEventListener("submit", () => {
    const data = new FormData(form);
    setTimingDetailsVisible(data.has("user_show_timing_details"));
  });
  settingsOutput.appendChild(form);
}

function renderSettingsProcessing() {
  const p = state.settings.processing || {};
  const formats = state.settings.processing_formats?.length
    ? state.settings.processing_formats
    : ["JPG", "PNG", "WEBP", "BMP", "GIF", "TIFF"];
  const form = document.createElement("form");
  form.className = "settings-form";
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent =
    "Te ustawienia sa stosowane przy zapisie z panelu webowego. FIT w slocie nadal moze byc wlaczany osobno dla pojedynczego zdjecia.";
  form.append(
    note,
    settingsFieldGroup("FIT slotu",
      checkField(
        "auto_content_fit",
        "FIT domyslnie dla kazdego slotu",
        state.settings.auto_content_fit,
        "Nowe i wczytane sloty startuja z wlaczonym FIT, ale pojedynczy slot nadal mozna przelaczyc."
      )
    ),
    settingsFieldGroup("Przetwarzanie uploadu",
      selectField(
        "upload_processing_mode",
        "Kiedy przetwarzac obrazy",
        p.upload_processing_mode || "save",
        [
          ["save", "Host przy zapisie"],
          ["host", "Host przy uploadzie do cache"],
          ["client", "Klient przed uploadem"],
        ]
      )
    ),
    settingsFieldGroup("Zmniejszanie obrazu",
      checkField(
        "resize_enabled",
        "Wlacz zmniejszanie",
        p.resize_enabled,
        "Najdluzszy bok obrazu zostanie ograniczony do podanej liczby pikseli."
      ),
      inputField("max_dim", "Maksymalny bok (px)", p.max_dim || 2000, {
        type: "number",
        min: 64,
        max: 20000,
      })
    ),
    settingsFieldGroup("Kompresja JPG/WEBP",
      checkField(
        "compress_enabled",
        "Wlacz kompresje",
        p.compress_enabled,
        "Uzywa podanej jakosci przy zapisie stratnych formatow."
      ),
      inputField("compress_quality", "Jakosc (%)", p.compress_quality || 85, {
        type: "number",
        min: 1,
        max: 100,
      })
    ),
    settingsFieldGroup("Limit rozmiaru pliku",
      checkField(
        "max_size_enabled",
        "Wlacz limit rozmiaru",
        p.max_size_enabled,
        "Dla JPG/WEBP jakosc jest obnizana stopniowo, az plik miesci sie w limicie."
      ),
      inputField("max_file_kb", "Maksymalny rozmiar (KB)", p.max_file_kb || 500, {
        type: "number",
        min: 1,
        max: 102400,
      })
    ),
    settingsFieldGroup("Konwersja formatu",
      checkField(
        "convert_enabled",
        "Wlacz konwersje",
        p.convert_enabled,
        "Obrazy sa zapisywane w wybranym formacie zamiast w formacie zrodlowym."
      ),
      selectField(
        "target_format",
        "Format docelowy",
        p.target_format || "PNG",
        formats.map((format) => [format, format])
      )
    )
  );
  settingsSaveButton(form, (data) => ({
    app: {
      auto_content_fit: data.has("auto_content_fit"),
    },
    processing: {
      resize_enabled: data.has("resize_enabled"),
      max_dim: data.get("max_dim"),
      compress_enabled: data.has("compress_enabled"),
      compress_quality: data.get("compress_quality"),
      max_size_enabled: data.has("max_size_enabled"),
      max_file_kb: data.get("max_file_kb"),
      convert_enabled: data.has("convert_enabled"),
      target_format: data.get("target_format"),
      upload_processing_mode: data.get("upload_processing_mode"),
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsSecurity() {
  const security = state.settings.security || {};
  const form = document.createElement("form");
  form.className = "settings-form";
  const secretHint = document.createElement("p");
  secretHint.className = "settings-note";
  secretHint.textContent =
    "APP_SECRET sluzy do odczytu zaszyfrowanych hasel z config.json. " +
    "Przy podpinaniu istniejacego katalogu wpisz sekret uzyty przy jego konfiguracji; puste pole niczego nie zmienia.";
  form.append(
    settingsFieldGroup("Sekret aplikacji",
      secretHint,
      credentialField("app_secret", "APP_SECRET", state.settings.app_secret_set, {
        type: "password",
        secretPath: "app_secret",
      })
    ),
    settingsFieldGroup("Limity uploadu",
      inputField("max_upload_mb", "Maksymalny upload (MB)", security.max_upload_mb || 50, {
        type: "number",
        min: 1,
        max: 2048,
        description: "Backend przerwie zapis i usunie czesciowy plik po przekroczeniu limitu.",
      }),
      inputField(
        "max_upload_pixels",
        "Maksymalna liczba pikseli",
        security.max_upload_pixels || 25000000,
        {
          type: "number",
          min: 1,
          max: 400000000,
          step: 100000,
          description: "Dotyczy obrazow z uploadu, cache, rozszerzenia i importu z URL.",
        }
      )
    ),
    settingsFieldGroup("Typy plikow uploadu",
      inputField(
        "allowed_upload_extensions",
        "Akceptowane rozszerzenia",
        extensionListText(security.allowed_upload_extensions),
        {
          textarea: true,
          description:
            "Lista po przecinku. Gdy ma wpisy, wszystko spoza niej jest odrzucane. " +
            "Pusta lista wylacza allow-liste, ale nadal dzialaja blokady ponizej.",
        }
      ),
      inputField(
        "blocked_upload_extensions",
        "Zabronione rozszerzenia",
        extensionListText(security.blocked_upload_extensions),
        {
          textarea: true,
          description: "Lista po przecinku. Te typy sa odrzucane niezaleznie od listy akceptowanych.",
        }
      ),
      checkField(
        "block_executable_uploads",
        "Blokuj pliki wykonywalne",
        security.block_executable_uploads !== false,
        "Odrzuca m.in. exe, bat, cmd, msi, ps1, vbs, js, jar, dll, scr, sh."
      ),
      checkField(
        "antivirus_scan_uploads",
        "Skanuj upload Microsoft Defender",
        Boolean(security.antivirus_scan_uploads),
        "Dotyczy tylko plikow wysylanych przez panel lub rozszerzenie; pliki juz lokalne i pobrane z FTP nie sa ponownie skanowane."
      ),
      checkField(
        "show_active_web_users",
        "Pokaz aktywnych uzytkownikow",
        Boolean(security.show_active_web_users),
        "Uzytkownicy zobacza nazwy kont obecnie aktywnych w panelu WWW."
      )
    )
  );
  settingsSaveButton(form, (data) => ({
    security: {
      app_secret: data.get("app_secret"),
      max_upload_mb: data.get("max_upload_mb"),
      max_upload_pixels: data.get("max_upload_pixels"),
      allowed_upload_extensions: data.get("allowed_upload_extensions"),
      blocked_upload_extensions: data.get("blocked_upload_extensions"),
      block_executable_uploads: data.has("block_executable_uploads"),
      antivirus_scan_uploads: data.has("antivirus_scan_uploads"),
      show_active_web_users: data.has("show_active_web_users"),
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsFtp() {
  const ftp = state.settings.ftp;
  const form = document.createElement("form");
  form.className = "settings-form";
  form.append(
    settingsFieldGroup("Polaczenie FTP",
      checkField(
        "enabled",
        "Aktualizacja FTP",
        ftp.enabled,
        "Po zapisie backend bedzie wysylal przetworzone pliki na FTP."
      ),
      inputField("host", "Host", ftp.host),
      inputField("port", "Port", ftp.port, { type: "number" }),
      inputField("path", "Sciezka", ftp.path),
      actionRow(diagnosticButton("ftp", "Test FTP"))
    ),
    settingsFieldGroup("Dane logowania FTP",
      credentialField("user", "Uzytkownik", ftp.user_set, { secretPath: "ftp.user" }),
      credentialField("password", "Haslo", ftp.password_set, {
        type: "password",
        secretPath: "ftp.password",
      })
    )
  );
  settingsSaveButton(form, (data) => ({
    ftp: {
      enabled: data.has("enabled"),
      host: data.get("host"),
      port: data.get("port"),
      path: data.get("path"),
      user: data.get("user"),
      password: data.get("password"),
    },
  }));
  settingsOutput.appendChild(form);
}

function sqlPlaceholderHelp(items = []) {
  const wrapper = document.createElement("div");
  wrapper.className = "settings-note sql-placeholder-help";
  wrapper.append("Dostepne placeholdery SQL: ");
  for (const [token, label] of items) {
    const code = document.createElement("code");
    code.textContent = token;
    wrapper.append(code, ` ${label}; `);
  }
  return wrapper;
}

function sqlProfileRow(profile = {}) {
  const row = document.createElement("div");
  row.className = "sql-profile-card sql-profile-row";
  row.dataset.profileId = profile.id || "";
  row.append(
    inputField("profile_label", "Nazwa profilu", profile.label || ""),
    selectField("profile_type", "Typ bazy", profile.type || "mysql", [
      ["mysql", "MySQL"],
      ["mssql", "MS SQL"],
    ]),
    inputField("profile_host", "Serwer", profile.host || ""),
    inputField("profile_database", "Baza", profile.database || ""),
    credentialField("profile_user", "Uzytkownik", profile.user_set, {
      secretPath: `database.profiles.${profile.id}.user`,
    }),
    credentialField("profile_password", "Haslo", profile.password_set, {
      type: "password",
      secretPath: `database.profiles.${profile.id}.password`,
    }),
    checkField("profile_enabled", "Aktywny", profile.enabled !== false)
  );
  if (profile.locked) {
    row.querySelectorAll("input, select").forEach((field) => {
      field.disabled = true;
    });
  }
  const test = document.createElement("button");
  test.type = "button";
  test.className = "secondary-button";
  test.textContent = "Test profilu";
  test.addEventListener("click", async () => {
    test.disabled = true;
    try {
      const result = await requestJson(
        `/api/settings/sql-profiles/${encodeURIComponent(profile.id || "")}/test`,
        { method: "POST" }
      );
      settingsStatus.textContent = result.message || "";
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      test.disabled = false;
    }
  });
  row.appendChild(test);
  if (!profile.locked) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost-button";
    remove.textContent = "Usun";
    remove.addEventListener("click", () => row.remove());
    row.appendChild(remove);
  }
  return row;
}

function collectSqlProfiles(form) {
  return Array.from(form.querySelectorAll(".sql-profile-row"))
    .filter((row) => row.dataset.profileId !== "default")
    .map((row) => ({
      id: row.dataset.profileId || row.querySelector('[name="profile_label"]').value,
      label: row.querySelector('[name="profile_label"]').value,
      type: row.querySelector('[name="profile_type"]').value,
      host: row.querySelector('[name="profile_host"]').value,
      database: row.querySelector('[name="profile_database"]').value,
      user: row.querySelector('[name="profile_user"]').value,
      password: row.querySelector('[name="profile_password"]').value,
      enabled: row.querySelector('[name="profile_enabled"]').checked,
    }));
}

function renderSettingsSql() {
  const db = state.settings.database;
  const form = document.createElement("form");
  const profiles = document.createElement("div");
  const addProfile = document.createElement("button");
  const placeholderItems = [
    ["{ean}", "EAN aktualnego produktu"],
    ["{filename}", "Nazwa wygenerowanego pliku"],
    ["{col}", "Kolumna SQL przypisana do slotu"],
    ["{column}", "Alias dla {col}"],
  ];
  profiles.className = "sql-profile-list wide-field";
  for (const profile of additionalSqlProfiles(db)) {
    profiles.appendChild(sqlProfileRow(profile));
  }
  addProfile.type = "button";
  addProfile.className = "secondary-button";
  addProfile.textContent = "Dodaj profil Pimcore SQL";
  addProfile.addEventListener("click", () => {
    profiles.appendChild(
      sqlProfileRow({
        id: `profile-${Date.now()}`,
        label: "Nowy profil",
        type: "mysql",
        enabled: true,
      })
    );
  });
  form.className = "settings-form";
  form.append(
    settingsFieldGroup("Tryb SQL",
      selectField("type", "Typ bazy", db.type, [["mysql", "MySQL"], ["mssql", "MS SQL"]]),
      checkField(
        "sql_update_enabled",
        "Aktualizacja SQL",
        db.sql_update_enabled,
        "Backend bedzie aktualizowal pola SQL przypisane w zakladce Sloty."
      ),
      inputField("query", "Zapytanie SQL", db.query, { textarea: true }),
      sqlPlaceholderHelp(placeholderItems),
      actionRow(diagnosticButton("sql", "Test SQL")),
      settingsNote("Domyslne polaczenie dla zdjec i slotow."),
      inputField("mssql_server", "MS SQL server", db.mssql.server),
      inputField("mssql_database", "MS SQL database", db.mssql.database),
      credentialField("mssql_user", "MS SQL user", db.mssql.user_set, {
        secretPath: "database.mssql.user",
      }),
      credentialField("mssql_password", "MS SQL haslo", db.mssql.password_set, {
        type: "password",
        secretPath: "database.mssql.password",
      }),
      inputField("mysql_server", "MySQL server", db.mysql.server),
      inputField("mysql_database", "MySQL database", db.mysql.database),
      credentialField("mysql_user", "MySQL user", db.mysql.user_set, {
        secretPath: "database.mysql.user",
      }),
      credentialField("mysql_password", "MySQL haslo", db.mysql.password_set, {
        type: "password",
        secretPath: "database.mysql.password",
      })
    ),
    settingsFieldGroup("Profile dodatkowe SQL",
      settingsNote("Niezalezne profile uzywane tylko po wybraniu w builderze wartosci pola Pimcore."),
      profiles,
      actionRow(addProfile)
    )
  );
  settingsSaveButton(form, (data) => ({
    database: {
      type: data.get("type"),
      sql_update_enabled: data.has("sql_update_enabled"),
      query: data.get("query"),
      mssql: {
        server: data.get("mssql_server"),
        database: data.get("mssql_database"),
        user: data.get("mssql_user"),
        password: data.get("mssql_password"),
      },
      mysql: {
        server: data.get("mysql_server"),
        database: data.get("mysql_database"),
        user: data.get("mysql_user"),
        password: data.get("mysql_password"),
      },
      profiles: collectSqlProfiles(form),
    },
  }));
  settingsOutput.appendChild(form);
}

const PIMCORE_TEMPLATE_PRODUCT_SOURCES = [
  ["Nazwa", "PRODUCT:name"],
  ["Typ", "PRODUCT:type"],
  ["Model", "PRODUCT:model"],
  ["Kolor 1", "PRODUCT:color1"],
  ["Kolor 2", "PRODUCT:color2"],
  ["Kolor 3", "PRODUCT:color3"],
  ["Dodatek", "PRODUCT:extra"],
  ["EAN", "PRODUCT:ean"],
];

const PIMCORE_TEMPLATE_FUNCTIONS = [
  ["Bez zmiany", "|keep"],
  ["Przytnij spacje", "|trim"],
  ["Ujednolic spacje", "|normalize_spaces"],
  ["WIELKIE LITERY", "|upper"],
  ["male litery", "|lower"],
  ["Kazde Slowo", "|title"],
  ["Pierwsza litera", "|capitalize"],
  ["Bez polskich znakow", "|strip_diacritics"],
  ["Slug", "|slug"],
  ["Zamien tekst", '|replace:"stary","nowy"'],
  ["Wartosc awaryjna", '|default:"brak"'],
  ["Fragment", "|substring:0,10"],
  ["Skroc", '|truncate:30,"..."'],
  ["Liczba", '|number:2,","," "'],
];

const PIMCORE_TEMPLATE_MATH_TOKENS = [
  ["Oblicz", "oblicz()"],
  ["Dodaj", "+"],
  ["Odejmij", "-"],
  ["Mnoz", "*"],
  ["Dziel", "/"],
];

function pimcoreFieldLanguage(value = {}) {
  return String(value?.language || "").trim();
}

function pimcoreFieldSource(name, language) {
  const fieldName = String(name || "").trim();
  const fieldLanguage = String(language || "").trim();
  if (!fieldName || !fieldLanguage) return fieldName;
  const suffix = `_${fieldLanguage.toUpperCase()}`;
  return fieldName.toUpperCase().endsWith(suffix) ? fieldName : `${fieldName}${suffix}`;
}

function pimcoreFieldOptionText(field = {}) {
  const language = pimcoreFieldLanguage(field);
  const label = field.label || field.name || "";
  const localized =
    language && !String(label).includes(`[${language}]`) ? ` [${language}]` : "";
  return `${label}${localized} - ${field.type || "input"}`;
}

function pimcoreFieldsMatch(field = {}, mapping = {}) {
  return (
    String(field.name || "") === String(mapping.pimcore_field || "") &&
    pimcoreFieldLanguage(field) === pimcoreFieldLanguage(mapping)
  );
}

function pimcoreSelectedMappingSource(select) {
  const option = select?.selectedOptions?.[0];
  return pimcoreFieldSource(select?.value || "", option?.dataset.language || "");
}

function pimcoreTemplateLanguageForRow(row) {
  if (!row) return "";
  if (row.classList.contains("pimcore-setup-field-row")) {
    return row.dataset.fieldLanguage || "";
  }
  if (row.classList.contains("pimcore-simple-mapping-row")) {
    return row.querySelector('[name="mapping_target"]')?.selectedOptions[0]?.dataset.language || "";
  }
  return row.querySelector('[name="mapping_language"]')?.value.trim() || "";
}

function pimcoreTemplateBuilderButton(row) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost-button pimcore-template-button";
  button.textContent = "Konstruuj";
  button.addEventListener("click", () => openPimcoreTemplateBuilder(row));
  return button;
}

function pimcoreTemplateFieldType(row) {
  if (row.classList.contains("pimcore-setup-field-row")) {
    return row.dataset.fieldType || "input";
  }
  if (row.classList.contains("pimcore-simple-mapping-row")) {
    return row.querySelector('[name="mapping_target"]')?.selectedOptions[0]?.dataset.type || "input";
  }
  return row.querySelector('[name="mapping_type"]')?.value || "input";
}

function updatePimcoreTemplateButton(row) {
  const button = row.querySelector(".pimcore-template-button");
  if (!button) return;
  const supported = ["input", "textarea", "select"].includes(pimcoreTemplateFieldType(row));
  button.disabled = !supported;
  button.textContent = row.dataset.valueTemplate ? "Zmien szablon" : "Konstruuj";
  button.title = supported
    ? "Zbuduj automatyczna wartosc pola"
    : "Szablony sa dostepne tylko dla pol tekstowych";
}

function pimcoreTemplateSource(row) {
  if (row.classList.contains("pimcore-setup-field-row")) {
    const eanTarget =
      row.closest(".pimcore-setup-body")?.querySelector('[name="ean_target"]')?.value ||
      state.pimcoreSetup?.eanTarget;
    return row.dataset.fieldName === eanTarget
      ? "EAN"
      : pimcoreFieldSource(row.dataset.fieldName, row.dataset.fieldLanguage);
  }
  if (row.classList.contains("pimcore-simple-mapping-row")) {
    return (
      row.dataset.source ||
      pimcoreSelectedMappingSource(row.querySelector('[name="mapping_target"]'))
    );
  }
  return row.querySelector('[name="mapping_source"]')?.value.trim() || "";
}

function pimcoreTemplateMappings(row) {
  const form = row.closest("form");
  if (row.classList.contains("pimcore-setup-field-row")) {
    const use = row.querySelector('[name="mapping_use"]');
    if (use && !use.disabled) use.checked = true;
    return collectPimcoreSetupMappings(row.closest(".pimcore-setup-body"));
  }
  if (row.classList.contains("pimcore-simple-mapping-row")) {
    const use = row.querySelector('[name="mapping_use"]');
    if (use) use.checked = true;
    return collectSimplePimcoreMappings(form);
  }
  return collectPimcoreMappings(form);
}

function insertPimcoreTemplateText(text, { wrap = false } = {}) {
  if (!pimcoreTemplateText) return;
  const start = pimcoreTemplateText.selectionStart ?? pimcoreTemplateText.value.length;
  const end = pimcoreTemplateText.selectionEnd ?? start;
  const selected = pimcoreTemplateText.value.slice(start, end);
  const inserted = wrap ? `(${selected})` : text;
  pimcoreTemplateText.setRangeText(inserted, start, end, "end");
  if (wrap && !selected) {
    pimcoreTemplateText.setSelectionRange(start + 1, start + 1);
  }
  pimcoreTemplateText.focus();
}

function insertPimcoreTemplateFunction(token) {
  if (!pimcoreTemplateText) return;
  const value = pimcoreTemplateText.value;
  const start = pimcoreTemplateText.selectionStart ?? value.length;
  const end = pimcoreTemplateText.selectionEnd ?? start;
  const selected = value.slice(start, end);
  if (selected.startsWith("{") && selected.endsWith("}")) {
    pimcoreTemplateText.setRangeText(
      `${selected.slice(0, -1)}${token}}`,
      start,
      end,
      "end"
    );
  } else {
    const before = value.slice(0, start);
    const position = before.endsWith("}") ? start - 1 : start;
    pimcoreTemplateText.setRangeText(token, position, position, "end");
  }
  pimcoreTemplateText.focus();
}

function insertPimcoreTemplateSqlToken() {
  insertPimcoreTemplateText("{SQL|keep}");
}

function renderPimcoreTemplateTokens(row) {
  pimcoreTemplateSources.textContent = "";
  pimcoreTemplateFunctions.textContent = "";
  for (const [label, source] of PIMCORE_TEMPLATE_PRODUCT_SOURCES) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = `{${label}}`;
    button.addEventListener("click", () => insertPimcoreTemplateText(`{${source}|keep}`));
    pimcoreTemplateSources.appendChild(button);
  }
  const targetSource = pimcoreTemplateSource(row);
  for (const mapping of pimcoreTemplateMappings(row)) {
    if (!mapping.source || mapping.source === targetSource) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = `{${mapping.label || mapping.source}}`;
    button.title = `Pole Pimcore: ${mapping.source}`;
    button.addEventListener("click", () =>
      insertPimcoreTemplateText(`{PIMCORE:${mapping.source}|keep}`)
    );
    pimcoreTemplateSources.appendChild(button);
  }
  const group = document.createElement("button");
  group.type = "button";
  group.className = "ghost-button";
  group.textContent = "Nawiasy (...)";
  group.title = "Grupa warunkowa albo nawiasy dzialania";
  group.addEventListener("click", () => insertPimcoreTemplateText("", { wrap: true }));
  pimcoreTemplateFunctions.appendChild(group);
  const sql = document.createElement("button");
  sql.type = "button";
  sql.className = "ghost-button";
  sql.textContent = "SQL";
  sql.title = "{SQL|keep}";
  sql.addEventListener("click", insertPimcoreTemplateSqlToken);
  pimcoreTemplateFunctions.appendChild(sql);
  for (const [label, token] of PIMCORE_TEMPLATE_MATH_TOKENS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = label;
    button.title = token;
    button.addEventListener("click", () => insertPimcoreTemplateText(token));
    pimcoreTemplateFunctions.appendChild(button);
  }
  for (const [label, token] of PIMCORE_TEMPLATE_FUNCTIONS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ghost-button";
    button.textContent = label;
    button.title = token;
    button.addEventListener("click", () => insertPimcoreTemplateFunction(token));
    pimcoreTemplateFunctions.appendChild(button);
  }
}

function renderPimcoreTemplateSqlControls(row) {
  if (!pimcoreTemplateSqlControls) return;
  pimcoreTemplateSqlControls.textContent = "";
  pimcoreTemplateSqlControls.classList.add("pimcore-template-sql-controls");
  pimcoreTemplateSqlControls.appendChild(
    pimcoreSqlMappingControls(row, {
      sql_query: row.dataset.sqlQuery || "",
      sql_profile_id: row.dataset.sqlProfileId || "",
    })
  );
}

function pimcoreTemplateSqlValues() {
  return {
    sql_query:
      pimcoreTemplateSqlControls?.querySelector('[name="mapping_sql_query"]')?.value || "",
    sql_profile_id:
      pimcoreTemplateSqlControls?.querySelector('[name="mapping_sql_profile_id"]')?.value || "",
  };
}

function openPimcoreTemplateBuilder(row) {
  if (!row || !pimcoreTemplateModal || pimcoreTemplateFieldType(row) === "checkbox") return;
  state.pimcoreTemplateRow = row;
  pimcoreTemplateText.value = row.dataset.valueTemplate || "";
  pimcoreTemplateTranslate.checked = row.dataset.translate === "true";
  pimcoreTemplateLanguage.value = row.dataset.targetLanguage || pimcoreTemplateLanguageForRow(row);
  pimcoreTemplateLanguage.disabled = !pimcoreTemplateTranslate.checked;
  pimcoreTemplateTarget.textContent = `Pole: ${pimcoreTemplateSource(row) || "nowe mapowanie"}`;
  pimcoreTemplatePreview.textContent = "Wpisz szablon i uruchom podglad.";
  pimcoreTemplateStatus.textContent = "";
  renderPimcoreTemplateSqlControls(row);
  renderPimcoreTemplateTokens(row);
  pimcoreTemplateModal.classList.add("active");
  pimcoreTemplateText.focus();
}

function pimcoreTemplatePreviewPayload() {
  const row = state.pimcoreTemplateRow;
  const targetSource = pimcoreTemplateSource(row);
  const mappings = pimcoreTemplateMappings(row);
  const target = mappings.find((mapping) => mapping.source === targetSource);
  if (!target) throw new Error("Najpierw wybierz pole Pimcore dla tego mapowania.");
  target.value_template = pimcoreTemplateText.value;
  Object.assign(target, pimcoreTemplateSqlValues());
  target.translate = pimcoreTemplateTranslate.checked;
  target.target_language =
    pimcoreTemplateLanguage.value.trim() || pimcoreTemplateLanguageForRow(row) || null;
  return {
    mappings,
    target_source: targetSource,
    product_values: formPayload(),
    values: Object.fromEntries(mappings.map((mapping) => [mapping.source, mapping.default || ""])),
  };
}

async function previewPimcoreTemplate() {
  pimcoreTemplatePreviewButton.disabled = true;
  pimcoreTemplateStatus.textContent = "Przeliczanie...";
  try {
    const payload = pimcoreTemplatePreviewPayload();
    const result = await requestJson("/api/settings/pimcore/template-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    pimcoreTemplatePreview.textContent = result.values?.[payload.target_source] ?? "";
    pimcoreTemplateStatus.textContent = (result.warnings || [])
      .map((warning) => warning.message || warning.code)
      .filter(Boolean)
      .join(" ");
  } catch (error) {
    pimcoreTemplatePreview.textContent = "Nie mozna wygenerowac podgladu.";
    pimcoreTemplateStatus.textContent = error.message;
  } finally {
    pimcoreTemplatePreviewButton.disabled = false;
  }
}

function savePimcoreTemplateBuilder() {
  const row = state.pimcoreTemplateRow;
  if (!row) return;
  const template = pimcoreTemplateText.value.trim();
  const translate = pimcoreTemplateTranslate.checked;
  const language = pimcoreTemplateLanguage.value.trim() || pimcoreTemplateLanguageForRow(row);
  if (translate && !template) {
    pimcoreTemplateStatus.textContent = "Tlumaczenie wymaga szablonu.";
    return;
  }
  if (translate && !language) {
    pimcoreTemplateStatus.textContent = "Podaj jezyk docelowy tlumaczenia.";
    return;
  }
  row.dataset.valueTemplate = template;
  const sqlValues = pimcoreTemplateSqlValues();
  row.dataset.sqlQuery = sqlValues.sql_query;
  row.dataset.sqlProfileId = sqlValues.sql_profile_id;
  row.dataset.translate = translate ? "true" : "false";
  row.dataset.targetLanguage = translate ? language : "";
  if (translate) pimcoreTemplateLanguage.value = language;
  updatePimcoreTemplateButton(row);
  closePimcoreTemplateBuilder();
}

function closePimcoreTemplateBuilder() {
  pimcoreTemplateModal?.classList.remove("active");
  if (pimcoreTemplateSqlControls) pimcoreTemplateSqlControls.textContent = "";
  state.pimcoreTemplateRow = null;
}

function additionalSqlProfiles(db = {}) {
  return (db.profiles || []).filter((profile) => profile.usage === "pimcore_sql");
}

function sqlProfileOptions(selected = "") {
  const options = additionalSqlProfiles(state.settings?.database || {})
    .filter((profile) => profile.enabled !== false)
    .map((profile) => [profile.id, profile.label || profile.id]);
  if (selected && !options.some(([id]) => id === selected)) {
    options.push([selected, selected]);
  }
  return options;
}

function pimcoreSqlMappingControls(row, mapping = {}) {
  const wrapper = document.createElement("div");
  const query = inputField("mapping_sql_query", "Zapytanie SQL", mapping.sql_query || "", {
    textarea: true,
  });
  const profile = selectField(
    "mapping_sql_profile_id",
    "Profil SQL",
    mapping.sql_profile_id || "",
    [["", "Wybierz profil"]].concat(sqlProfileOptions(mapping.sql_profile_id || ""))
  );
  wrapper.className = "pimcore-sql-mapping-controls";
  wrapper.append(query, profile);
  return wrapper;
}

function pimcoreMappingRow(mapping = {}) {
  const row = document.createElement("div");
  row.dataset.valueTemplate = mapping.value_template || "";
  row.dataset.translate = mapping.translate ? "true" : "false";
  row.dataset.targetLanguage = mapping.target_language || "";
  row.dataset.sqlQuery = mapping.sql_query || "";
  row.dataset.sqlProfileId = mapping.sql_profile_id || "";
  row.className = "pimcore-mapping-row";
  const textInput = (name, value, label) => {
    const input = document.createElement("input");
    input.name = name;
    input.value = value || "";
    input.placeholder = label;
    input.setAttribute("aria-label", label);
    return input;
  };
  const choice = (name, value, values, label) => {
    const select = document.createElement("select");
    select.name = name;
    select.setAttribute("aria-label", label);
    for (const item of values) {
      const option = document.createElement("option");
      option.value = item;
      option.textContent = item;
      option.selected = item === value;
      select.appendChild(option);
    }
    return select;
  };
  const required = document.createElement("input");
  required.type = "checkbox";
  required.name = "mapping_required";
  required.checked = Boolean(mapping.required);
  required.setAttribute("aria-label", "Pole wymagane");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "ghost-button";
  remove.textContent = "Usun";
  remove.title = "Usun mapowanie";
  remove.addEventListener("click", () => row.remove());
  const template = pimcoreTemplateBuilderButton(row);
  row.append(
    textInput("mapping_source", mapping.source, "Kolumna CSV"),
    textInput("mapping_label", mapping.label, "Etykieta"),
    textInput("mapping_target", mapping.pimcore_field, "Pole Pimcore"),
    choice(
      "mapping_type",
      mapping.type || "input",
      ["input", "textarea", "numeric", "checkbox", "select"],
      "Typ Pimcore"
    ),
    textInput("mapping_language", mapping.language, "Jezyk"),
    required,
    textInput("mapping_default", mapping.default, "Wartosc domyslna"),
    choice(
      "mapping_parser",
      mapping.parser || "text",
      ["text", "integer", "decimal_comma", "boolean", "empty_to_null"],
      "Parser"
    ),
    template,
    remove
  );
  return row;
}

function collectPimcoreMappings(form) {
  return [...form.querySelectorAll(".pimcore-mapping-row")].map((row) => ({
    source: row.querySelector('[name="mapping_source"]').value.trim(),
    label: row.querySelector('[name="mapping_label"]').value.trim(),
    pimcore_field: row.querySelector('[name="mapping_target"]').value.trim(),
    type: row.querySelector('[name="mapping_type"]').value,
    language: row.querySelector('[name="mapping_language"]').value.trim() || null,
    required: row.querySelector('[name="mapping_required"]').checked,
    default: row.querySelector('[name="mapping_default"]').value,
    parser: row.querySelector('[name="mapping_parser"]').value,
    value_template: row.dataset.valueTemplate || "",
    sql_query: row.querySelector('[name="mapping_sql_query"]')?.value || row.dataset.sqlQuery || "",
    sql_profile_id:
      row.querySelector('[name="mapping_sql_profile_id"]')?.value || row.dataset.sqlProfileId || "",
    translate: row.dataset.translate === "true",
    target_language: row.dataset.targetLanguage || null,
  }));
}

function collectPimcoreSettings(form) {
  const data = new FormData(form);
  return {
    enabled: data.has("enabled"),
    base_url: data.get("base_url"),
    api_key: data.get("api_key"),
    class_name: data.get("class_name"),
    parent_id: data.get("parent_id"),
    published: data.has("published"),
    object_key_template: data.get("object_key_template"),
    existence_fields: String(data.get("existence_fields") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    timeout_seconds: Number(data.get("timeout_seconds") || 10),
    verify_tls: data.has("verify_tls"),
    field_mappings: collectPimcoreMappings(form),
  };
}

function pimcoreCompactClassItems(pimcore = {}) {
  const items = Array.isArray(state.pimcoreSetup?.classes) ? [...state.pimcoreSetup.classes] : [];
  if (
    pimcore.class_id &&
    !items.some((item) => String(item.id) === String(pimcore.class_id))
  ) {
    items.push({ id: pimcore.class_id, name: pimcore.class_name || pimcore.class_id });
  }
  return items;
}

function pimcoreCompactFolderItems(pimcore = {}) {
  const items = Array.isArray(state.pimcoreSetup?.folders) ? [...state.pimcoreSetup.folders] : [];
  if (
    pimcore.parent_id &&
    !items.some((item) => String(item.id) === String(pimcore.parent_id))
  ) {
    items.push({
      id: pimcore.parent_id,
      key: pimcore.parent_path || pimcore.parent_id,
      path: pimcore.parent_path || pimcore.parent_id,
    });
  }
  return items;
}

function pimcoreCompactFields(pimcore = {}) {
  const discovered = Array.isArray(state.pimcoreSetup?.fields) ? state.pimcoreSetup.fields : [];
  const fields = discovered.length ? [...discovered] : [];
  for (const mapping of pimcore.field_mappings || []) {
    if (
      mapping.pimcore_field &&
      !fields.some((field) => pimcoreFieldsMatch(field, mapping))
    ) {
      fields.push({
        name: mapping.pimcore_field,
        label: mapping.label || mapping.pimcore_field,
        type: mapping.type || "input",
        parser: mapping.parser || "text",
        language: mapping.language || "",
        supported: true,
      });
    }
  }
  return fields;
}

function pimcoreSimpleMappingRow(mapping = {}, fields = []) {
  const row = document.createElement("div");
  const use = document.createElement("input");
  const label = document.createElement("input");
  const target = document.createElement("select");
  const required = document.createElement("input");
  const remove = document.createElement("button");
  const template = pimcoreTemplateBuilderButton(row);
  const isEan = String(mapping.source || "").toUpperCase() === "EAN";
  const availableFields = [...fields];
  row.className = "pimcore-simple-mapping-row";
  use.type = "checkbox";
  use.name = "mapping_use";
  use.checked = true;
  use.setAttribute("aria-label", "Uzyj pola");
  label.name = "mapping_label";
  label.value = mapping.label || mapping.source || "";
  label.placeholder = "Etykieta";
  label.setAttribute("aria-label", "Etykieta");
  target.name = "mapping_target";
  target.setAttribute("aria-label", "Pole Pimcore");
  if (
    mapping.pimcore_field &&
    !availableFields.some((field) => pimcoreFieldsMatch(field, mapping))
  ) {
    availableFields.push({
      name: mapping.pimcore_field,
      label: mapping.pimcore_field,
      type: mapping.type || "input",
      parser: mapping.parser || "text",
      language: mapping.language || "",
      supported: true,
    });
  }
  for (const field of availableFields) {
    const option = document.createElement("option");
    option.value = field.name;
    option.textContent = pimcoreFieldOptionText(field);
    option.disabled = field.supported === false;
    option.selected = pimcoreFieldsMatch(field, mapping);
    option.dataset.type = field.type || "input";
    option.dataset.parser = field.parser || "text";
    option.dataset.language = field.language || "";
    if (field.unsupported_reason) option.title = field.unsupported_reason;
    target.appendChild(option);
  }
  required.type = "checkbox";
  required.name = "mapping_required";
  required.checked = isEan || Boolean(mapping.required);
  required.disabled = isEan;
  required.setAttribute("aria-label", "Pole wymagane");
  remove.type = "button";
  remove.className = "ghost-button";
  remove.textContent = "Usun";
  remove.disabled = isEan;
  remove.addEventListener("click", () => row.remove());
  row.dataset.source = isEan ? "EAN" : String(mapping.source || mapping.pimcore_field || "");
  row.dataset.valueTemplate = mapping.value_template || "";
  row.dataset.translate = mapping.translate ? "true" : "false";
  row.dataset.targetLanguage = mapping.target_language || "";
  row.dataset.sqlQuery = mapping.sql_query || "";
  row.dataset.sqlProfileId = mapping.sql_profile_id || "";
  target.addEventListener("change", () => {
    if (!row.dataset.source && !label.value.trim()) {
      label.value = pimcoreSelectedMappingSource(target);
    }
    updatePimcoreTemplateButton(row);
  });
  row.append(use, label, target, required, template, remove);
  updatePimcoreTemplateButton(row);
  return row;
}

function collectSimplePimcoreMappings(form) {
  return [...form.querySelectorAll(".pimcore-simple-mapping-row")]
    .filter((row) => row.querySelector('[name="mapping_use"]')?.checked)
    .map((row) => {
      const select = row.querySelector('[name="mapping_target"]');
      const option = select?.selectedOptions[0];
      const source = row.dataset.source || pimcoreSelectedMappingSource(select);
      return {
        source,
        label: row.querySelector('[name="mapping_label"]').value.trim() || source,
        pimcore_field: select?.value || "",
        type: option?.dataset.type || "input",
        language: option?.dataset.language || null,
        required:
          String(source).toUpperCase() === "EAN" ||
          row.querySelector('[name="mapping_required"]').checked,
        default: "",
        parser: option?.dataset.parser || "text",
        value_template: row.dataset.valueTemplate || "",
        sql_query:
          row.querySelector('[name="mapping_sql_query"]')?.value || row.dataset.sqlQuery || "",
        sql_profile_id:
          row.querySelector('[name="mapping_sql_profile_id"]')?.value ||
          row.dataset.sqlProfileId ||
          "",
        translate: row.dataset.translate === "true",
        target_language: row.dataset.targetLanguage || null,
      };
    })
    .filter((mapping) => mapping.source && mapping.pimcore_field);
}

function collectCompactPimcoreSettings(form) {
  const data = new FormData(form);
  const classSelect = form.querySelector('[name="class_id"]');
  const parentSelect = form.querySelector('[name="parent_id"]');
  const selectedClass = classSelect?.selectedOptions[0];
  const selectedParent = parentSelect?.selectedOptions[0];
  const mappings = collectSimplePimcoreMappings(form);
  const manualClassId = String(data.get("manual_class_id") || "").trim();
  const manualClassName = String(data.get("manual_class_name") || "").trim();
  const manualParentId = String(data.get("manual_parent_id") || "").trim();
  const manualParentPath = String(data.get("manual_parent_path") || "").trim();
  return {
    setup_complete: true,
    enabled: data.has("enabled"),
    base_url: data.get("base_url"),
    api_key: data.get("api_key"),
    class_id: manualClassId || classSelect?.value || "",
    class_name: manualClassName || selectedClass?.dataset.name || "",
    parent_id: manualParentId || parentSelect?.value || "",
    parent_path: manualParentPath || selectedParent?.dataset.path || "",
    published: true,
    object_key_template: "{EAN}",
    existence_fields: mappings
      .filter((item) => String(item.source).toUpperCase() === "EAN")
      .map((item) => item.pimcore_field),
    timeout_seconds: Number(data.get("timeout_seconds") || 30),
    verify_tls: data.has("verify_tls"),
    field_mappings: collectSimplePimcoreMappings(form),
  };
}

function pimcoreManualCompactLocationFields(pimcore = {}) {
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const grid = document.createElement("div");
  summary.textContent = "Wpisz klase i folder recznie";
  grid.className = "pimcore-setup-grid";
  grid.append(
    inputField("manual_class_name", "Nazwa klasy", "", {
      placeholder: pimcore.class_name || "Product",
    }),
    inputField("manual_class_id", "ID klasy", "", {
      placeholder: pimcore.class_id || "",
    }),
    inputField("manual_parent_id", "ID folderu", "", {
      placeholder: pimcore.parent_id || "",
    }),
    inputField("manual_parent_path", "Sciezka folderu", "", {
      placeholder: pimcore.parent_path || "/Products",
    })
  );
  details.className = "wide-field";
  details.append(summary, grid);
  return details;
}

async function requestPimcoreSettingsDiscovery(kind, settings, extra = {}) {
  const payload = await requestJson(PIMCORE_DISCOVERY_ENDPOINTS[kind], {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings, ...extra }),
    timeoutMs: 120000,
  });
  return Array.isArray(payload.items) ? payload.items : [];
}

async function refreshCompactPimcoreMetadata(form, button) {
  const snapshot = collectCompactPimcoreSettings(form);
  button.disabled = true;
  settingsStatus.textContent = "Pobieranie klas i folderow Pimcore...";
  try {
    const classes = await requestPimcoreSettingsDiscovery("classes", snapshot);
    const folders = await requestPimcoreSettingsDiscovery("folders", snapshot);
    const classId = snapshot.class_id || classes[0]?.id || "";
    const fields = classId
      ? await requestPimcoreSettingsDiscovery("fields", snapshot, { class_id: classId })
      : [];
    state.pimcoreSetup = {
      ...(state.pimcoreSetup || {}),
      settings: snapshot,
      classes,
      folders,
      fields,
      mappings: snapshot.field_mappings || [],
    };
    state.settings.pimcore = { ...(state.settings.pimcore || {}), ...snapshot };
    settingsStatus.textContent =
      `Pobrano ${classes.length} klas, ${folders.length} folderow i ${fields.length} pol.`;
    renderSettings();
  } catch (error) {
    settingsStatus.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

function pimcoreCsvImportButton(mappingList, fields = []) {
  const input = document.createElement("input");
  const button = document.createElement("button");
  const wrapper = document.createElement("span");
  input.type = "file";
  input.accept = ".csv,text/csv";
  input.hidden = true;
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Wczytaj naglowki CSV";
  button.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const body = new FormData();
      body.set("file", file, file.name);
      const payload = await requestJson("/api/settings/pimcore/import-csv-headers", {
        method: "POST",
        body,
      });
      const existing = new Set(
        [...mappingList.querySelectorAll('[name="mapping_source"], [name="mapping_label"]')]
          .map((item) => item.value)
      );
      for (const header of payload.headers || []) {
        if (!existing.has(header)) {
          if (mappingList.classList.contains("pimcore-simple-mapping-list")) {
            mappingList.appendChild(pimcoreSimpleMappingRow({ source: header, label: header }, fields));
          } else {
            mappingList.appendChild(pimcoreMappingRow({ source: header, label: header }));
          }
          existing.add(header);
        }
      }
      settingsStatus.textContent = `Wczytano ${(payload.headers || []).length} naglowkow CSV.`;
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      input.value = "";
    }
  });
  wrapper.append(button, input);
  return wrapper;
}

function pimcoreChecklistElement() {
  const output = document.createElement("div");
  output.id = "pimcoreSettingsChecklist";
  output.className = "pimcore-checklist empty-state";
  output.textContent = "Test nie zostal uruchomiony.";
  return output;
}

function renderPimcoreChecklist(report = {}, target = null) {
  const output = target || document.querySelector("#pimcoreSettingsChecklist");
  if (!output) return;
  output.textContent = "";
  output.className = "pimcore-checklist";
  const checks = Array.isArray(report.checks) ? report.checks : [];
  if (!checks.length) {
    output.className = "pimcore-checklist empty-state";
    output.textContent = report.ok ? "Test zakonczony bez dodatkowych komunikatow." : "Brak wynikow testu.";
    return;
  }
  for (const check of checks) {
    const row = document.createElement("div");
    const title = document.createElement("strong");
    const status = check.status || "info";
    row.className = `pimcore-check-row ${status}`;
    if (status === "skipped") {
      row.setAttribute("aria-disabled", "true");
    }
    title.textContent = `${status}: ${check.message || check.key || "kontrola"}`;
    const technical = [
      check.endpoint,
      check.status_code ? `HTTP ${check.status_code}` : "",
      `${Number(check.elapsed_ms || 0)} ms`,
      check.response_excerpt,
      check.suggested_fix,
    ]
      .filter(Boolean);
    row.appendChild(title);
    if (technical.length) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      const detail = document.createElement("pre");
      summary.textContent = "Szczegoly techniczne";
      detail.textContent = technical.join("\n");
      details.append(summary, detail);
      row.appendChild(details);
    }
    output.appendChild(row);
  }
}

const PIMCORE_DISCOVERY_ENDPOINTS = {
  classes: "/api/settings/pimcore/discover/classes",
  folders: "/api/settings/pimcore/discover/folders",
  fields: "/api/settings/pimcore/discover/fields",
};

function pimcoreDiscoveryErrorText(error) {
  const detail = error?.detail && typeof error.detail === "object" ? error.detail : {};
  const technical = [
    detail.status_code ? `HTTP ${detail.status_code}` : "",
    detail.response_excerpt || "",
  ].filter(Boolean);
  return technical.length ? `${error.message} Szczegoly: ${technical.join(" | ")}` : error.message;
}

function settingsNote(text) {
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent = text;
  return note;
}

function pimcoreSetupInput(name, labelText, value = "", type = "text", placeholder = "") {
  const label = document.createElement("label");
  const title = document.createElement("span");
  const input = document.createElement("input");
  title.textContent = labelText;
  input.name = name;
  input.type = type;
  input.value = value || "";
  input.placeholder = placeholder;
  input.autocomplete = type === "password" ? "new-password" : "off";
  label.append(title, input);
  return label;
}

function pimcoreSetupSelect(name, labelText, items, selected, valueKey, textBuilder) {
  const label = document.createElement("label");
  const title = document.createElement("span");
  const select = document.createElement("select");
  const placeholder = document.createElement("option");
  title.textContent = labelText;
  select.name = name;
  placeholder.value = "";
  placeholder.textContent = "Wybierz...";
  placeholder.disabled = true;
  placeholder.selected = !selected;
  select.appendChild(placeholder);
  for (const item of items) {
    const option = document.createElement("option");
    option.value = String(item[valueKey] ?? "");
    option.textContent = textBuilder(item);
    option.selected = option.value === String(selected || "");
    if (item.name) option.dataset.name = item.name;
    if (item.path) option.dataset.path = item.path;
    select.appendChild(option);
  }
  label.append(title, select);
  return label;
}

function openPimcoreSetupWizard() {
  const saved = state.settings?.pimcore || {};
  state.pimcoreSetup = {
    step: 1,
    settings: { ...saved, api_key: "" },
    classes: [],
    folders: [],
    fields: [],
    mappings: Array.isArray(saved.field_mappings) ? [...saved.field_mappings] : [],
    manualLocation: false,
    eanTarget:
      (saved.field_mappings || []).find((item) => item.source === "EAN")?.pimcore_field || "",
    report: null,
  };
  pimcoreSetupModal?.classList.add("active");
  renderPimcoreSetupStep();
}

function renderPimcoreSetupStep() {
  const setup = state.pimcoreSetup;
  if (!setup || !pimcoreSetupBody) return;
  const titles = {
    1: "Krok 1 z 4: Polaczenie",
    2: "Krok 2 z 4: Miejsce zapisu",
    3: "Krok 3 z 4: Pola produktu",
    4: "Krok 4 z 4: Test i zapis",
  };
  pimcoreSetupBody.textContent = "";
  if (pimcoreSetupStepTitle) pimcoreSetupStepTitle.textContent = titles[setup.step] || titles[1];
  [...(pimcoreSetupProgress?.children || [])].forEach((item, index) => {
    item.classList.toggle("active", index + 1 === setup.step);
  });
  const renderers = {
    1: renderPimcoreConnectionStep,
    2: renderPimcoreLocationStep,
    3: renderPimcoreFieldsStep,
    4: renderPimcoreVerifyStep,
  };
  renderers[setup.step]();
  if (pimcoreSetupBackButton) pimcoreSetupBackButton.disabled = setup.step === 1;
  if (pimcoreSetupNextButton) {
    pimcoreSetupNextButton.textContent =
      setup.step === 4 ? "Zapisz i wlacz integracje" : "Dalej";
  }
}

function renderPimcoreConnectionStep() {
  const setup = state.pimcoreSetup;
  const grid = document.createElement("div");
  const test = document.createElement("button");
  const manual = document.createElement("button");
  grid.className = "pimcore-setup-grid";
  grid.append(
    pimcoreSetupInput(
      "base_url",
      "Adres Pimcore",
      setup.settings.base_url,
      "text",
      "http://twoj-adres-pimcore.example"
    ),
    pimcoreSetupInput("api_key", "Klucz API", setup.settings.api_key || "", "password")
  );
  test.type = "button";
  test.className = "secondary-button";
  test.textContent = "Sprawdz polaczenie i pobierz klasy";
  test.addEventListener("click", async () => {
    capturePimcoreSetupStep();
    test.disabled = true;
    try {
      setup.classes = await requestPimcoreDiscovery("classes");
      if (pimcoreSetupStatus) {
        pimcoreSetupStatus.textContent = `Pobrano ${setup.classes.length} klas.`;
      }
    } catch (error) {
      if (pimcoreSetupStatus) pimcoreSetupStatus.textContent = pimcoreDiscoveryErrorText(error);
    } finally {
      test.disabled = false;
    }
  });
  manual.type = "button";
  manual.className = "ghost-button";
  manual.textContent = "Kontynuuj z recznym wpisaniem klasy i folderu";
  manual.addEventListener("click", () => {
    capturePimcoreSetupStep();
    if (!setup.settings.base_url || (!setup.settings.api_key && !state.settings?.pimcore?.api_key_set)) {
      if (pimcoreSetupStatus) pimcoreSetupStatus.textContent = "Podaj adres Pimcore i klucz API.";
      return;
    }
    setup.manualLocation = true;
    setup.step = 2;
    renderPimcoreSetupStep();
  });
  pimcoreSetupBody.append(grid, actionRow(test, manual));
}

function renderPimcoreLocationStep() {
  const setup = state.pimcoreSetup;
  const grid = document.createElement("div");
  const refresh = document.createElement("button");
  grid.className = "pimcore-setup-grid";
  grid.append(
    pimcoreSetupSelect(
      "class_id",
      "Klasa produktu",
      setup.classes,
      setup.settings.class_id,
      "id",
      (item) => `${item.name} (ID ${item.id})`
    ),
    pimcoreSetupSelect(
      "parent_id",
      "Folder docelowy",
      setup.folders,
      setup.settings.parent_id,
      "id",
      (item) => `${item.path || item.key} (ID ${item.id})`
    )
  );
  refresh.type = "button";
  refresh.className = "secondary-button";
  refresh.textContent = "Odswiez foldery";
  refresh.addEventListener("click", async () => {
    capturePimcoreSetupStep();
    try {
      setup.folders = await requestPimcoreDiscovery("folders");
      renderPimcoreSetupStep();
    } catch (error) {
      if (pimcoreSetupStatus) {
        pimcoreSetupStatus.textContent = `${pimcoreDiscoveryErrorText(error)} Wpisz ID folderu recznie.`;
      }
    }
  });
  pimcoreSetupBody.append(grid, refresh);
  if (!setup.folders.length) {
    pimcoreSetupBody.append(
      settingsNote(
        "Nie wykryto folderow Pimcore. Otworz sekcje ponizej i wpisz ID folderu recznie; sciezka folderu jest opcjonalna."
      )
    );
  }
  pimcoreSetupBody.append(pimcoreManualLocationFallback());
}

function renderPimcoreFieldsStep() {
  const setup = state.pimcoreSetup;
  const supported = setup.fields.filter((field) => field.supported);
  if (!setup.eanTarget) {
    setup.eanTarget = supported.find((field) => field.name.toUpperCase() === "EAN")?.name || "";
  }
  const eanTarget = pimcoreSetupSelect(
    "ean_target",
    "Pole EAN w Pimcore",
    supported,
    setup.eanTarget,
    "name",
    (item) => `${item.label || item.name} (${item.name})`
  );
  const intro = document.createElement("p");
  const eanHelp = document.createElement("p");
  const header = document.createElement("div");
  intro.className = "settings-note";
  intro.textContent =
    "Ktore dane uzytkownik ma wpisywac podczas dodawania produktu? Zaznacz Zapisz pole tylko dla potrzebnych danych.";
  eanHelp.className = "settings-note";
  eanHelp.textContent =
    "Lista Pole EAN w Pimcore wskazuje kolumne, w ktorej Pimcore przechowuje 13-cyfrowy EAN.";
  header.className = "pimcore-setup-field-header";
  for (const text of ["Zapisz pole", "Pole w Pimcore", "Nazwa w formularzu", "Wymagane", "Wartosc"]) {
    const cell = document.createElement("strong");
    cell.textContent = text;
    header.appendChild(cell);
  }
  const table = document.createElement("div");
  table.className = "pimcore-setup-field-list";
  table.appendChild(header);
  for (const field of setup.fields) {
    table.appendChild(pimcoreSetupFieldRow(field, setup.mappings, setup.eanTarget));
  }
  eanTarget.querySelector("select").addEventListener("change", (event) => {
    setup.mappings = collectPimcoreSetupMappings(pimcoreSetupBody).filter(
      (item) => item.source !== "EAN"
    );
    setup.eanTarget = event.target.value;
    renderPimcoreSetupStep();
  });
  pimcoreSetupBody.append(intro, eanTarget, eanHelp, table);
}

function renderPimcoreVerifyStep() {
  const run = document.createElement("button");
  const output = document.createElement("div");
  output.className = "pimcore-checklist empty-state";
  output.textContent = "Test nie zostal uruchomiony.";
  run.type = "button";
  run.className = "secondary-button";
  run.textContent = "Sprawdz konfiguracje";
  run.addEventListener("click", async () => {
    const report = await requestJson("/api/settings/pimcore/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: buildPimcoreSetupPayload() }),
      timeoutMs: 120000,
    });
    state.pimcoreSetup.report = report;
    renderPimcoreChecklist(report, output);
    if (pimcoreSetupNextButton) pimcoreSetupNextButton.disabled = !report.ok;
  });
  if (pimcoreSetupNextButton) {
    pimcoreSetupNextButton.disabled = !state.pimcoreSetup.report?.ok;
  }
  pimcoreSetupBody.append(run, output);
}

function pimcoreManualLocationFallback() {
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const grid = document.createElement("div");
  const setup = state.pimcoreSetup;
  const classKnown = setup.classes.some(
    (item) => String(item.id) === String(setup.settings.class_id || "")
  );
  const folderKnown = setup.folders.some(
    (item) => String(item.id) === String(setup.settings.parent_id || "")
  );
  summary.textContent = "Wpisz wartosci recznie";
  grid.className = "pimcore-setup-grid";
  grid.append(
    pimcoreSetupInput("manual_class_name", "Nazwa klasy", classKnown ? "" : setup.settings.class_name),
    pimcoreSetupInput("manual_class_id", "ID klasy", classKnown ? "" : setup.settings.class_id),
    pimcoreSetupInput("manual_parent_id", "ID folderu", folderKnown ? "" : setup.settings.parent_id),
    pimcoreSetupInput(
      "manual_parent_path",
      "Sciezka folderu",
      folderKnown ? "" : setup.settings.parent_path
    )
  );
  details.append(summary, grid);
  return details;
}

function pimcoreSetupFieldRow(field, mappings, eanTarget) {
  const existing = mappings.find((item) => pimcoreFieldsMatch(field, item)) || {};
  const row = document.createElement("div");
  const use = document.createElement("input");
  const label = document.createElement("input");
  const required = document.createElement("input");
  const useLabel = document.createElement("label");
  const fieldName = document.createElement("code");
  const labelWrapper = document.createElement("label");
  const requiredLabel = document.createElement("label");
  const isEan = field.name === eanTarget;
  row.className = "pimcore-setup-field-row";
  row.dataset.fieldName = field.name;
  row.dataset.fieldType = field.type;
  row.dataset.fieldLanguage = field.language || "";
  row.dataset.fieldParser = field.parser || "";
  row.dataset.valueTemplate = existing.value_template || "";
  row.dataset.translate = existing.translate ? "true" : "false";
  row.dataset.targetLanguage = existing.target_language || "";
  row.dataset.sqlQuery = existing.sql_query || "";
  row.dataset.sqlProfileId = existing.sql_profile_id || "";
  use.type = "checkbox";
  use.name = "mapping_use";
  use.checked = isEan || Boolean(existing.pimcore_field);
  use.disabled = !field.supported || isEan;
  label.name = "mapping_label";
  label.value = existing.label || field.label || field.name;
  label.disabled = !field.supported;
  required.type = "checkbox";
  required.name = "mapping_required";
  required.checked = isEan || Boolean(existing.required);
  required.disabled = isEan || !field.supported;
  use.setAttribute("aria-label", `Zapisz pole ${field.name}`);
  required.setAttribute("aria-label", `Pole ${field.name} wymagane`);
  useLabel.append(use, document.createTextNode(" Zapisz"));
  fieldName.textContent = field.language ? `${field.name} [${field.language}]` : field.name;
  labelWrapper.append(label);
  requiredLabel.append(required, document.createTextNode(" Wymagane"));
  const template = pimcoreTemplateBuilderButton(row);
  row.append(useLabel, fieldName, labelWrapper, requiredLabel, template);
  updatePimcoreTemplateButton(row);
  if (!field.supported) row.title = field.unsupported_reason || "Pole nie jest obslugiwane.";
  return row;
}

function collectPimcoreSetupMappings(container) {
  const eanTarget =
    container.querySelector('[name="ean_target"]')?.value || state.pimcoreSetup.eanTarget;
  return [...container.querySelectorAll(".pimcore-setup-field-row")]
    .filter(
      (row) =>
        row.dataset.fieldName === eanTarget ||
        row.querySelector('[name="mapping_use"]')?.checked
    )
    .map((row) => {
      const source =
        row.dataset.fieldName === eanTarget
          ? "EAN"
          : pimcoreFieldSource(row.dataset.fieldName, row.dataset.fieldLanguage);
      return {
        source,
        label: row.querySelector('[name="mapping_label"]').value.trim() || source,
        pimcore_field: row.dataset.fieldName,
        type: row.dataset.fieldType,
        language: row.dataset.fieldLanguage || null,
        required: source === "EAN" || row.querySelector('[name="mapping_required"]').checked,
        default: "",
        parser: row.dataset.fieldParser,
        value_template: row.dataset.valueTemplate || "",
        sql_query:
          row.querySelector('[name="mapping_sql_query"]')?.value || row.dataset.sqlQuery || "",
        sql_profile_id:
          row.querySelector('[name="mapping_sql_profile_id"]')?.value ||
          row.dataset.sqlProfileId ||
          "",
        translate: row.dataset.translate === "true",
        target_language: row.dataset.targetLanguage || null,
      };
    });
}

function capturePimcoreSetupStep() {
  const setup = state.pimcoreSetup;
  if (!setup || !pimcoreSetupForm) return;
  const data = new FormData(pimcoreSetupForm);
  for (const key of ["base_url", "api_key", "class_id", "parent_id"]) {
    if (data.has(key)) setup.settings[key] = String(data.get(key) || "").trim();
  }
  if (setup.step === 2) {
    const selectedClass = setup.classes.find((item) => String(item.id) === setup.settings.class_id);
    const selectedFolder = setup.folders.find((item) => String(item.id) === setup.settings.parent_id);
    if (selectedClass) setup.settings.class_name = selectedClass.name;
    if (selectedFolder) setup.settings.parent_path = selectedFolder.path;
    const manualClassId = String(data.get("manual_class_id") || "").trim();
    const manualClassName = String(data.get("manual_class_name") || "").trim();
    const manualParentId = String(data.get("manual_parent_id") || "").trim();
    const manualParentPath = String(data.get("manual_parent_path") || "").trim();
    if (manualClassId || manualClassName) {
      setup.settings.class_id = manualClassId;
      setup.settings.class_name = manualClassName;
    }
    if (manualParentId) {
      setup.settings.parent_id = manualParentId;
      setup.settings.parent_path = manualParentPath;
    }
  }
  if (setup.step === 3) setup.mappings = collectPimcoreSetupMappings(pimcoreSetupBody);
}

function buildPimcoreSetupPayload() {
  const setup = state.pimcoreSetup;
  return {
    ...setup.settings,
    enabled: true,
    setup_complete: false,
    published: true,
    object_key_template: "{EAN}",
    field_mappings: setup.mappings,
  };
}

async function requestPimcoreDiscovery(kind, extra = {}) {
  const setup = state.pimcoreSetup;
  return requestPimcoreSettingsDiscovery(kind, setup.settings, extra);
}

async function advancePimcoreSetup() {
  const setup = state.pimcoreSetup;
  if (!setup) return;
  if (pimcoreSetupStatus) pimcoreSetupStatus.textContent = "";
  capturePimcoreSetupStep();
  try {
    if (setup.step === 1) {
      if (!setup.settings.base_url || (!setup.settings.api_key && !state.settings?.pimcore?.api_key_set)) {
        throw new Error("Podaj adres Pimcore i klucz API.");
      }
      if (!setup.classes.length) {
        setup.classes = await requestPimcoreDiscovery("classes");
      }
      if (!setup.classes.length) throw new Error("Nie znaleziono klas Pimcore.");
      try {
        setup.folders = await requestPimcoreDiscovery("folders");
      } catch (error) {
        setup.folders = [];
        if (pimcoreSetupStatus) {
          pimcoreSetupStatus.textContent = `Nie pobrano folderow: ${error.message}. Wpisz folder recznie.`;
        }
      }
      setup.step = 2;
    } else if (setup.step === 2) {
      if (!setup.settings.class_id || !setup.settings.class_name || !setup.settings.parent_id) {
        throw new Error("Wybierz klase produktu i folder docelowy albo wpisz je recznie.");
      }
      setup.fields = await requestPimcoreDiscovery("fields", {
        class_id: setup.settings.class_id,
      });
      if (!setup.fields.length) throw new Error("Klasa nie udostepnia pol do przypisania.");
      setup.step = 3;
    } else if (setup.step === 3) {
      const ean = setup.mappings.find((item) => item.source === "EAN" && item.required);
      if (!ean) throw new Error("Wybierz wymagane pole EAN.");
      setup.report = null;
      setup.step = 4;
    } else {
      await savePimcoreSetup();
      return;
    }
    renderPimcoreSetupStep();
  } catch (error) {
    if (pimcoreSetupStatus) pimcoreSetupStatus.textContent = error.message;
  }
}

async function savePimcoreSetup() {
  if (pimcoreSetupNextButton) pimcoreSetupNextButton.disabled = true;
  if (pimcoreSetupStatus) pimcoreSetupStatus.textContent = "Zapisywanie konfiguracji...";
  try {
    const result = await requestJson("/api/settings/pimcore/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ settings: buildPimcoreSetupPayload() }),
      timeoutMs: 120000,
    });
    state.settings = result.settings || state.settings;
    pimcoreSetupModal?.classList.remove("active");
    renderSettingsPimcore();
  } catch (error) {
    if (pimcoreSetupStatus) pimcoreSetupStatus.textContent = error.message;
  } finally {
    if (pimcoreSetupNextButton) pimcoreSetupNextButton.disabled = false;
  }
}

function pimcoreReadOnlyTestButton(getSettings) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Sprawdz konfiguracje";
  button.addEventListener("click", async () => {
    button.disabled = true;
    settingsStatus.textContent = "Testowanie Pimcore...";
    try {
      const report = await requestJson("/api/settings/pimcore/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: getSettings() }),
        timeoutMs: 120000,
      });
      renderPimcoreChecklist(report);
      settingsStatus.textContent = report.ok
        ? "Test konfiguracji Pimcore zakonczony powodzeniem."
        : "Test konfiguracji Pimcore wykryl problemy.";
    } catch (error) {
      settingsStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

function pimcoreOpenWriteTestButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Testowo dodaj obiekt";
  button.addEventListener("click", openPimcoreWriteTest);
  return button;
}

function pimcoreHistoryButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = "Historia Pimcore";
  button.addEventListener("click", () => {
    openPimcoreHistory().catch((error) => {
      if (pimcoreHistoryOutput) {
        pimcoreHistoryOutput.className = "history-output empty-state";
        pimcoreHistoryOutput.textContent = error.message;
      }
    });
  });
  return button;
}

function populatePimcoreRuntimeForm(
  form,
  schema,
  values = {},
  { readOnlySources = [], allowRecalculate = false, status = null, idPrefix = "pimcoreField" } = {}
) {
  if (!form) return;
  form.textContent = "";
  const readOnly = new Set(readOnlySources);
  for (const mapping of schema || []) {
    const label = document.createElement("label");
    const heading = document.createElement("span");
    const input = document.createElement("input");
    const fieldRow = document.createElement("span");
    label.className = "pimcore-runtime-field";
    heading.textContent = `${mapping.label || mapping.source}${mapping.required ? " *" : ""}`;
    input.name = mapping.source;
    input.value = values?.[mapping.source] ?? mapping.default ?? "";
    input.dataset.originalValue = input.value;
    input.required = Boolean(mapping.required);
    input.readOnly = readOnly.has(mapping.source);
    input.autocomplete = "off";
    const legacyEanIds = {
      pimcoreCreate: "pimcoreCreateEan",
      pimcoreEdit: "pimcoreEditEan",
    };
    input.id =
      mapping.source === "EAN" && legacyEanIds[idPrefix]
        ? legacyEanIds[idPrefix]
        : `${idPrefix}-${String(mapping.source || "field").replace(/[^A-Za-z0-9_-]/g, "-")}`;
    input.addEventListener("input", () => updatePimcoreRuntimeFieldChangeState(input));
    fieldRow.className = "pimcore-runtime-field-row";
    fieldRow.appendChild(input);
    if (allowRecalculate && mapping.value_template) {
      const recalculate = document.createElement("button");
      recalculate.type = "button";
      recalculate.className = "ghost-button icon-button pimcore-recalculate-field";
      recalculate.textContent = "↻";
      recalculate.title = `Przelicz pole ${mapping.label || mapping.source}`;
      recalculate.setAttribute("aria-label", recalculate.title);
      recalculate.addEventListener("click", async () => {
        recalculate.disabled = true;
        if (status) status.textContent = `Przeliczanie pola ${mapping.label || mapping.source}...`;
        try {
          const result = await renderPimcoreRuntimeTemplates(form, schema, [mapping.source]);
          if (status) status.textContent = pimcoreRuntimeRecalculateStatus(form, result);
        } catch (error) {
          if (status) status.textContent = error.message;
        } finally {
          recalculate.disabled = false;
        }
      });
      fieldRow.appendChild(recalculate);
    }
    label.append(heading, fieldRow);
    form.appendChild(label);
  }
}

function pimcoreRuntimeWarnings(warnings = []) {
  return warnings
    .map((warning) => warning.message || warning.code || "")
    .filter(Boolean)
    .join(" ");
}

function clearPimcoreRuntimeConflict(field) {
  if (!field) return;
  field.classList.remove("pimcore-runtime-conflict", "pimcore-runtime-pulse");
  const info = field.querySelector(".pimcore-runtime-calculated");
  if (info) info.hidden = true;
}

function updatePimcoreRuntimeOriginalState(input) {
  const form = input?.form;
  const field = input?.closest(".pimcore-runtime-field");
  if (!form || !field) return;
  const changed = form.dataset.pimcoreMode === "edit" && input.value !== input.dataset.originalValue;
  field.classList.toggle("pimcore-runtime-different", changed);
  let original = field.querySelector(".pimcore-runtime-original");
  if (!original) {
    original = document.createElement("span");
    original.className = "pimcore-runtime-original";
    const text = document.createElement("span");
    const undo = document.createElement("button");
    undo.type = "button";
    undo.className = "ghost-button";
    undo.textContent = "Cofnij zmiany";
    undo.addEventListener("click", () => {
      input.value = input.dataset.originalValue || "";
      clearPimcoreRuntimeConflict(field);
      updatePimcoreRuntimeFieldChangeState(input, { userInput: false });
    });
    original.append(text, undo);
    field.appendChild(original);
  }
  original.querySelector("span").textContent = `Oryginalnie: ${input.dataset.originalValue || "(puste)"}`;
  original.hidden = !changed;
}

function hasBlockingPimcoreRuntimeDifferences(form = pimcoreEditForm) {
  return Boolean(form?.querySelector(".pimcore-runtime-conflict"));
}

function pimcoreRuntimeDifferenceCount(form) {
  return form?.querySelectorAll(".pimcore-runtime-conflict").length || 0;
}

function focusFirstPimcoreRuntimeDifference(form = pimcoreEditForm) {
  const field = form?.querySelector(".pimcore-runtime-conflict");
  if (!field) return false;
  field.scrollIntoView({ behavior: "smooth", block: "center" });
  field.classList.remove("pimcore-runtime-pulse");
  void field.offsetWidth;
  field.classList.add("pimcore-runtime-pulse");
  const input = field.querySelector("input");
  if (input) input.focus({ preventScroll: true });
  window.setTimeout(() => field.classList.remove("pimcore-runtime-pulse"), 1800);
  return true;
}

function updatePimcoreRuntimeSubmitState(form, button) {
  if (!button || button.dataset.busy === "1") return;
  const blocked = hasBlockingPimcoreRuntimeDifferences(form);
  button.classList.toggle("pimcore-submit-blocked", blocked);
  button.setAttribute("aria-disabled", blocked ? "true" : "false");
  button.title = blocked
    ? "Najpierw zastosuj wyliczona wartosc albo cofnij zmiany w oznaczonej komorce."
    : "";
}

function updatePimcoreEditSubmitState() {
  updatePimcoreRuntimeSubmitState(pimcoreEditForm, pimcoreEditSubmitButton);
}

function updatePimcoreCreateSubmitState() {
  updatePimcoreRuntimeSubmitState(pimcoreCreateForm, pimcoreCreateSubmitButton);
}

function updatePimcoreRuntimeFieldChangeState(input, { userInput = true } = {}) {
  const field = input?.closest(".pimcore-runtime-field");
  updatePimcoreRuntimeOriginalState(input);
  if (userInput && field?.classList.contains("pimcore-runtime-conflict")) {
    const calculated = String(input.dataset.calculatedValue ?? "");
    const original = String(input.dataset.originalValue ?? "");
    if (String(input.value ?? "") === calculated || String(input.value ?? "") === original) {
      clearPimcoreRuntimeConflict(field);
    }
  }
  updatePimcoreCreateSubmitState();
  updatePimcoreEditSubmitState();
}

function updatePimcoreRuntimeCalculatedState(form, result = {}) {
  const calculated = result.calculated_values || {};
  const changed = result.changed || {};
  for (const [source, value] of Object.entries(calculated)) {
    const input = form.elements[source];
    if (!input) continue;
    const field = input.closest(".pimcore-runtime-field");
    if (!field) continue;
    input.dataset.calculatedValue = value ?? "";
    let info = field.querySelector(".pimcore-runtime-calculated");
    if (!info) {
      info = document.createElement("span");
      info.className = "pimcore-runtime-calculated";
      const text = document.createElement("span");
      const apply = document.createElement("button");
      apply.type = "button";
      apply.className = "ghost-button";
      apply.textContent = "Zastosuj wyliczone";
      apply.addEventListener("click", () => {
        input.value = input.dataset.calculatedValue || "";
        clearPimcoreRuntimeConflict(field);
        updatePimcoreRuntimeFieldChangeState(input, { userInput: false });
        info.hidden = true;
      });
      const undo = document.createElement("button");
      undo.type = "button";
      undo.className = "ghost-button";
      undo.textContent = "Cofnij zmiany";
      undo.addEventListener("click", () => {
        input.value = input.dataset.originalValue || "";
        clearPimcoreRuntimeConflict(field);
        updatePimcoreRuntimeFieldChangeState(input, { userInput: false });
      });
      info.append(text, apply, undo);
      field.appendChild(info);
    }
    info.querySelector("span").textContent = `Wyliczone: ${value ?? ""}`;
    const isDifferent = changed[source] === true && String(input.value) !== String(value ?? "");
    field.classList.toggle("pimcore-runtime-conflict", isDifferent);
    updatePimcoreRuntimeOriginalState(input);
    info.hidden = !isDifferent;
  }
  updatePimcoreCreateSubmitState();
  updatePimcoreEditSubmitState();
}

function pimcoreRuntimeRecalculateStatus(form, result = {}) {
  const warnings = pimcoreRuntimeWarnings(result.warnings);
  if (warnings) return warnings;
  const count = pimcoreRuntimeDifferenceCount(form);
  return count
    ? `Roznice po przeliczeniu: ${count}. Zastosuj wyliczone albo cofnij zmiany.`
    : "";
}

function blockPimcoreRuntimeSubmitIfNeeded(form, status) {
  if (!hasBlockingPimcoreRuntimeDifferences(form)) return false;
  focusFirstPimcoreRuntimeDifference(form);
  if (status) {
    status.textContent =
      "Najpierw zastosuj wyliczona wartosc albo cofnij zmiany w oznaczonej komorce.";
  }
  return true;
}

async function renderPimcoreRuntimeTemplates(form, schema, targets = null) {
  const selected = Array.isArray(targets)
    ? targets
    : (schema || []).filter((mapping) => mapping.value_template).map((mapping) => mapping.source);
  if (!selected.length) return { values: {}, warnings: [], calculated_values: {}, changed: {} };
  const values = Object.fromEntries(new FormData(form).entries());
  const result = await requestJson("/api/pimcore/render-templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      product_values: formPayload(),
      values,
      targets: selected,
      mode: form.dataset.pimcoreMode || "create",
    }),
  });
  for (const source of selected) {
    const input = form.elements[source];
    if (input && Object.prototype.hasOwnProperty.call(result.values || {}, source)) {
      if (!input.value) {
        input.value = result.values[source] ?? "";
      } else if (form.dataset.pimcoreMode === "apply") {
        input.value = result.values[source] ?? "";
      }
      updatePimcoreRuntimeFieldChangeState(input);
    }
  }
  updatePimcoreRuntimeCalculatedState(form, result);
  return result;
}

function pimcoreEditHasRuntimeTemplates() {
  return (state.pimcoreEditSchema || []).some((mapping) => mapping.value_template);
}

async function recalculateAllPimcoreEditFields() {
  if (!pimcoreEditForm || !pimcoreEditHasRuntimeTemplates()) return;
  if (pimcoreEditRecalculateAllButton) pimcoreEditRecalculateAllButton.disabled = true;
  if (pimcoreEditStatus) pimcoreEditStatus.textContent = "Przeliczanie wszystkich pol...";
  try {
    const result = await renderPimcoreRuntimeTemplates(pimcoreEditForm, state.pimcoreEditSchema);
    if (pimcoreEditStatus) {
      pimcoreEditStatus.textContent = pimcoreRuntimeRecalculateStatus(pimcoreEditForm, result);
    }
  } catch (error) {
    if (pimcoreEditStatus) pimcoreEditStatus.textContent = error.message;
  } finally {
    if (pimcoreEditRecalculateAllButton) {
      pimcoreEditRecalculateAllButton.disabled = !pimcoreEditHasRuntimeTemplates();
    }
  }
}

function openPimcoreWriteTest() {
  if (!pimcoreTestForm || !pimcoreTestModal) return;
  pimcoreTestModal.querySelectorAll('[name="pimcore_cleanup_policy"]').forEach((item) => {
    item.checked = false;
  });
  clearPimcoreLiveLog();
  pimcoreTestModal.classList.add("active");
  loadPimcoreTestSample();
}

async function loadPimcoreTestSample() {
  if (!pimcoreTestForm) return;
  pimcoreTestSubmitButton.disabled = true;
  pimcoreTestClearButton.disabled = true;
  pimcoreTestRegenerateButton.disabled = true;
  pimcoreTestStatus.textContent = "Generowanie unikalnych danych testowych...";
  try {
    const sample = await requestJson("/api/settings/pimcore/test-sample", { method: "POST" });
    pimcoreTestForm.dataset.pimcoreMode = "test";
    populatePimcoreRuntimeForm(
      pimcoreTestForm,
      sample.form_schema || [],
      sample.values || {},
      { idPrefix: "pimcoreTest" }
    );
    pimcoreTestStatus.textContent = pimcoreRuntimeWarnings(sample.warnings);
  } catch (error) {
    pimcoreTestForm.textContent = "";
    pimcoreTestStatus.textContent = `Nie mozna wygenerowac danych testowych: ${error.message}`;
  } finally {
    pimcoreTestSubmitButton.disabled = false;
    pimcoreTestClearButton.disabled = false;
    pimcoreTestRegenerateButton.disabled = false;
  }
}

function collectPimcoreTestValues() {
  if (!pimcoreTestForm) return {};
  return Object.fromEntries(
    [...pimcoreTestForm.querySelectorAll("input[name]")].map((input) => [input.name, input.value])
  );
}

function clearPimcoreLiveLog() {
  if (!pimcoreLiveLog || !pimcoreTestElapsed || !pimcoreTestStatus) return;
  pimcoreLiveLog.textContent = "Brak operacji.";
  pimcoreLiveLog.className = "pimcore-live-log empty-state";
  pimcoreTestElapsed.textContent = "0 ms";
  pimcoreTestStatus.textContent = "";
}

function appendPimcoreLiveEvents(events) {
  if (!pimcoreLiveLog) return;
  const wasAtBottom =
    pimcoreLiveLog.scrollHeight - pimcoreLiveLog.scrollTop - pimcoreLiveLog.clientHeight < 24;
  if (pimcoreLiveLog.classList.contains("empty-state")) {
    pimcoreLiveLog.textContent = "";
    pimcoreLiveLog.className = "pimcore-live-log";
  }
  for (const event of events || []) {
    const row = document.createElement("div");
    const heading = document.createElement("strong");
    const detail = document.createElement("span");
    const diagnostic = document.createElement("pre");
    row.className = `pimcore-live-event ${event.severity || "info"}`;
    const eventTime = Number(event.timestamp || 0) * 1000 || Date.now();
    heading.textContent =
      `[${new Date(eventTime).toLocaleTimeString()}] ${event.stage || "etap"}: ${event.message || ""}`;
    detail.textContent = [
      event.method,
      event.endpoint,
      event.status_code ? `HTTP ${event.status_code}` : "",
      `od startu ${Number(event.elapsed_ms || 0)} ms`,
      event.stage_elapsed_ms !== undefined ? `etap ${Number(event.stage_elapsed_ms || 0)} ms` : "",
    ]
      .filter(Boolean)
      .join(" | ");
    diagnostic.textContent = [
      event.response_excerpt,
      event.suggested_fix,
      event.error ? JSON.stringify(event.error, null, 2) : "",
    ]
      .filter(Boolean)
      .join("\n");
    row.append(heading, detail);
    if (diagnostic.textContent) row.appendChild(diagnostic);
    pimcoreLiveLog.appendChild(row);
  }
  if (wasAtBottom) pimcoreLiveLog.scrollTop = pimcoreLiveLog.scrollHeight;
}

function pimcoreTestObjectKey(template, values) {
  const missing = [];
  const rendered = String(template || "{EAN}").replace(/\{([^{}]+)\}/g, (_match, source) => {
    const value = String(values[source] || "").trim();
    if (!value) missing.push(source);
    return value;
  });
  if (missing.length) {
    throw new Error(`Brak wartosci dla klucza: ${[...new Set(missing)].join(", ")}`);
  }
  const key = rendered.replace(/[^0-9A-Za-z_.-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "");
  if (!key) throw new Error("Nie mozna zbudowac klucza obiektu Pimcore.");
  return key.slice(0, 190);
}

async function submitPimcoreWriteTest() {
  if (!pimcoreTestForm || !pimcoreTestModal) return;
  if (!pimcoreTestForm.reportValidity()) return;
  const cleanup =
    pimcoreTestModal.querySelector('[name="pimcore_cleanup_policy"]:checked')?.value || "";
  if (!cleanup) {
    throw new Error("Wybierz, czy obiekt ma zostac usuniety po tescie.");
  }
  const values = collectPimcoreTestValues();
  const target = state.settings?.pimcore || {};
  const objectKey = pimcoreTestObjectKey(target.object_key_template, values);
  if (
    !window.confirm(
      `Wyslac obiekt do ${target.base_url}, klasa ${target.class_name}, parent ${target.parent_id}, klucz ${objectKey}, tryb ${cleanup}?`
    )
  ) {
    return;
  }
  pimcoreTestSubmitButton.disabled = true;
  pimcoreTestClearButton.disabled = true;
  pimcoreTestRegenerateButton.disabled = true;
  clearPimcoreLiveLog();
  const payload = await requestJson("/api/settings/pimcore/test-create-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values, cleanup_policy: cleanup }),
  });
  state.pimcoreTestOperation = {
    operationId: payload.operation.operation_id,
    lastSequence: 0,
    active: true,
  };
  await pollPimcoreTestOperation();
}

async function pollPimcoreTestOperation() {
  const tracked = state.pimcoreTestOperation;
  if (!tracked?.active) return;
  try {
    const params = new URLSearchParams({ after_sequence: String(tracked.lastSequence || 0) });
    const payload = await requestJson(
      `/api/settings/pimcore/test-create-runs/${encodeURIComponent(tracked.operationId)}?${params.toString()}`
    );
    appendPimcoreLiveEvents(payload.events || []);
    for (const event of payload.events || []) {
      tracked.lastSequence = Math.max(tracked.lastSequence, Number(event.sequence || 0));
    }
    if (pimcoreTestElapsed) {
      pimcoreTestElapsed.textContent = formatDuration(payload.total_ms || 0);
    }
    if (["completed", "partial", "failed"].includes(payload.status)) {
      tracked.active = false;
      pimcoreTestSubmitButton.disabled = false;
      pimcoreTestClearButton.disabled = false;
      pimcoreTestRegenerateButton.disabled = false;
      pimcoreTestStatus.textContent = `Wynik: ${payload.status}. Operacja ${payload.operation_id}.`;
      return;
    }
  } catch (error) {
    appendPimcoreLiveEvents([
      {
        sequence: tracked.lastSequence,
        severity: "warning",
        stage: "poll",
        message: `Utrata polaczenia z logiem: ${error.message}`,
      },
    ]);
  }
  window.setTimeout(pollPimcoreTestOperation, 500);
}

function renderPimcoreHistory(items) {
  if (!pimcoreHistoryOutput) return;
  const rows = Array.isArray(items) ? items : [];
  pimcoreHistoryOutput.textContent = "";
  pimcoreHistoryOutput.className = rows.length ? "history-output" : "history-output empty-state";
  if (!rows.length) {
    pimcoreHistoryOutput.textContent = "Brak operacji Pimcore dla wybranego filtra.";
    return;
  }
  for (const item of rows) {
    const row = document.createElement("div");
    const toggle = document.createElement("button");
    const title = document.createElement("strong");
    const meta = document.createElement("span");
    const details = document.createElement("div");
    const resultPayload = item.result?.payload || {};
    row.className = "pimcore-history-row";
    toggle.type = "button";
    toggle.className = "history-summary-row";
    title.textContent = `${item.operation_type || "operacja"} | ${item.status || "unknown"} | ${
      item.operation_id || ""
    }`;
    meta.textContent = [
      item.started_at ? new Date(Number(item.started_at) * 1000).toLocaleString() : "",
      item.username,
      `${Number(item.total_ms || 0)} ms`,
      `klasa ${resultPayload.className || "brak"}`,
      `parent ${resultPayload.parentId || "brak"}`,
      `obiekt ${item.result?.object_id || item.result?.object?.id || "brak"}`,
      item.result?.object_path || item.result?.object?.path || "",
    ]
      .filter(Boolean)
      .join(" | ");
    details.className = "pimcore-history-event-details";
    details.hidden = true;
    for (const event of item.events || []) {
      const line = document.createElement("div");
      line.textContent = [
        `${event.sequence}. ${event.stage}: ${event.message}`,
        event.method,
        event.endpoint,
        event.status_code ? `HTTP ${event.status_code}` : "",
        `od startu ${Number(event.elapsed_ms || 0)} ms`,
        event.stage_elapsed_ms !== undefined ? `etap ${Number(event.stage_elapsed_ms || 0)} ms` : "",
        event.response_excerpt,
        event.suggested_fix,
      ]
        .filter(Boolean)
        .join(" | ");
      details.appendChild(line);
    }
    toggle.addEventListener("click", () => {
      details.hidden = !details.hidden;
    });
    toggle.append(title, meta);
    row.append(toggle, details);
    pimcoreHistoryOutput.appendChild(row);
  }
}

async function loadPimcoreHistory() {
  if (!pimcoreHistoryFilters) return;
  const data = new FormData(pimcoreHistoryFilters);
  const params = new URLSearchParams();
  for (const key of ["operation_type", "result", "user", "query"]) {
    const value = String(data.get(key) || "").trim();
    if (value) params.set(key, value);
  }
  const from = String(data.get("date_from") || "");
  const to = String(data.get("date_to") || "");
  if (from) params.set("date_from", String(new Date(`${from}T00:00:00`).getTime() / 1000));
  if (to) params.set("date_to", String(new Date(`${to}T23:59:59`).getTime() / 1000));
  const payload = await requestJson(`/api/settings/pimcore/operations?${params.toString()}`);
  renderPimcoreHistory(payload.items || []);
}

function pimcoreHistoryExportParams(format) {
  const data = new FormData(pimcoreHistoryFilters);
  const params = new URLSearchParams({ format });
  for (const key of ["operation_type", "result", "user", "query"]) {
    const value = String(data.get(key) || "").trim();
    if (value) params.set(key === "result" ? "status" : key, value);
  }
  const from = String(data.get("date_from") || "").trim();
  const to = String(data.get("date_to") || "").trim();
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  return params;
}

function exportPimcoreSubmissions(format) {
  const params = pimcoreHistoryExportParams(format);
  window.location.href = `/api/settings/pimcore/submissions/export?${params.toString()}`;
}

async function openPimcoreHistory() {
  if (!pimcoreHistoryModal) return;
  pimcoreHistoryModal.classList.add("active");
  await loadPimcoreHistory();
}

function applyPimcoreRuntimeCapabilities(capabilities = {}) {
  state.pimcoreRuntimeEnabled = capabilities.enabled === true;
  state.pimcoreExistingObject = null;
  state.pimcoreLastCheckedEan = "";
  if (pimcoreEditButton) {
    pimcoreEditButton.hidden = !state.pimcoreRuntimeEnabled;
    pimcoreEditButton.disabled = true;
  }
}

function handlePimcoreEanInput() {
  state.pimcoreExistingObject = null;
  state.pimcoreLastCheckedEan = "";
  if (pimcoreEditButton) pimcoreEditButton.disabled = true;
  if (!state.pimcoreRuntimeEnabled) return;
  schedulePimcoreStatusLookup();
}

function schedulePimcoreStatusLookup() {
  if (!state.pimcoreRuntimeEnabled) return;
  window.clearTimeout(state.pimcoreLookupTimer);
  const ean = productForm.elements.ean.value.trim();
  if (!/^\d{13}$/.test(ean) || ean === state.pimcoreLastCheckedEan) return;
  state.pimcoreLookupTimer = window.setTimeout(() => {
    checkPimcoreProductStatus(ean).catch((error) => {
      formStatus.textContent = `Nie mozna sprawdzic Pimcore: ${error.message}. Mozesz kontynuowac prace.`;
    });
  }, 500);
}

async function checkPimcoreProductStatus(ean) {
  const requestId = ++state.pimcoreLookupRequestId;
  const payload = await requestJson(`/api/pimcore/product-status?ean=${encodeURIComponent(ean)}`);
  if (requestId !== state.pimcoreLookupRequestId || productForm.elements.ean.value.trim() !== ean) {
    return;
  }
  state.pimcoreLastCheckedEan = ean;
  if (!payload.enabled) {
    state.pimcoreExistingObject = null;
    if (pimcoreEditButton) pimcoreEditButton.disabled = true;
    return;
  }
  if (payload.available === false) {
    state.pimcoreExistingObject = null;
    if (pimcoreEditButton) pimcoreEditButton.disabled = true;
    formStatus.textContent = `Pimcore niedostepny: ${payload.error?.message || "blad polaczenia"}`;
    return;
  }
  if (payload.exists) {
    const objectId = Number(payload.object?.id || 0);
    if (objectId > 0) {
      state.pimcoreExistingObject = payload.object || null;
      if (pimcoreEditButton) pimcoreEditButton.disabled = false;
      return;
    }
    state.pimcoreExistingObject = null;
    if (pimcoreEditButton) pimcoreEditButton.disabled = true;
    formStatus.textContent = "Pimcore zwrocil produkt bez poprawnego ID. Edycja jest niedostepna.";
    return;
  }
  state.pimcoreExistingObject = null;
  if (pimcoreEditButton) pimcoreEditButton.disabled = true;
  state.pimcoreCreateSchema = Array.isArray(payload.form_schema) ? payload.form_schema : [];
  state.pimcoreMissingEan = ean;
  pimcoreMissingMessage.textContent = `EAN ${ean} nie istnieje w Pimcore. Czy dodac produkt?`;
  pimcoreMissingModal.classList.add("active");
}

function openPimcoreCreateModal(ean) {
  if (!pimcoreCreateForm || !pimcoreCreateModal) return;
  pimcoreCreateForm.dataset.pimcoreMode = "create";
  const values = Object.fromEntries(
    (state.pimcoreCreateSchema || []).map((mapping) => [
      mapping.source,
      mapping.source === "EAN" ? ean : mapping.default || "",
    ])
  );
  populatePimcoreRuntimeForm(
    pimcoreCreateForm,
    state.pimcoreCreateSchema,
    values,
    {
      readOnlySources: ["EAN"],
      allowRecalculate: true,
      status: pimcoreCreateStatus,
      idPrefix: "pimcoreCreate",
    }
  );
  updatePimcoreCreateSubmitState();
  const pimcoreCreateEan = pimcoreCreateForm.querySelector("#pimcoreCreateEan");
  if (pimcoreCreateEan) pimcoreCreateEan.readOnly = true;
  if (pimcoreCreateStatus) pimcoreCreateStatus.textContent = "";
  pimcoreMissingModal?.classList.remove("active");
  pimcoreCreateModal.classList.add("active");
  renderPimcoreRuntimeTemplates(pimcoreCreateForm, state.pimcoreCreateSchema)
    .then((result) => {
      if (pimcoreCreateStatus) {
        pimcoreCreateStatus.textContent = pimcoreRuntimeRecalculateStatus(pimcoreCreateForm, result);
      }
    })
    .catch((error) => {
      if (pimcoreCreateStatus) {
        pimcoreCreateStatus.textContent = `Nie przeliczono szablonow: ${error.message}`;
      }
    });
}

async function submitPimcoreRuntimeCreate(event) {
  event.preventDefault();
  if (!pimcoreCreateForm.reportValidity()) return;
  if (blockPimcoreRuntimeSubmitIfNeeded(pimcoreCreateForm, pimcoreCreateStatus)) return;
  pimcoreCreateSubmitButton.disabled = true;
  pimcoreCreateStatus.textContent = "Zapisywanie w Pimcore...";
  try {
    const values = Object.fromEntries(new FormData(pimcoreCreateForm).entries());
    const payload = await requestJson("/api/pimcore/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
      timeoutMs: 120000,
    });
    const object = payload.object || {};
    pimcoreCreateModal.classList.remove("active");
    state.pimcoreLastCheckedEan = state.pimcoreMissingEan || values.EAN || "";
    formStatus.textContent = payload.duplicate
      ? `EAN juz istnieje w Pimcore: ${object.path || object.id}.`
      : `Utworzono produkt Pimcore: ${object.path || object.id}. Mozesz kontynuowac dodawanie zdjec.`;
  } catch (error) {
    pimcoreCreateStatus.textContent = error.message;
  } finally {
    pimcoreCreateSubmitButton.disabled = false;
  }
}

async function openPimcoreEditModal() {
  let objectId = Number(state.pimcoreExistingObject?.id || 0);
  if (objectId <= 0 && state.pimcoreRuntimeEnabled) {
    const currentEan = productForm.elements.ean.value.trim();
    if (/^\d{13}$/.test(currentEan)) {
      formStatus.textContent = "Sprawdzanie produktu Pimcore...";
      try {
        await checkPimcoreProductStatus(currentEan);
      } catch (error) {
        formStatus.textContent = `Nie mozna sprawdzic Pimcore: ${error.message}.`;
        return;
      }
      objectId = Number(state.pimcoreExistingObject?.id || 0);
    }
  }
  if (objectId <= 0) {
    formStatus.textContent = "Nie mozna edytowac produktu Pimcore bez poprawnego ID.";
    return;
  }
  if (!pimcoreEditForm || !pimcoreEditModal) return;
  const requestId = ++state.pimcoreEditRequestId;
  if (pimcoreEditButton) pimcoreEditButton.disabled = true;
  state.pimcoreEditObjectId = 0;
  state.pimcoreEditMarker = "";
  pimcoreEditForm.textContent = "";
  pimcoreEditObjectInfo.textContent = `ID ${objectId}`;
  pimcoreEditStatus.textContent = "Pobieranie danych Pimcore...";
  pimcoreEditSubmitButton.disabled = true;
  if (pimcoreEditRecalculateAllButton) pimcoreEditRecalculateAllButton.disabled = true;
  pimcoreEditModal.classList.add("active");
  try {
    const payload = await requestJson(`/api/pimcore/products/${encodeURIComponent(objectId)}`);
    if (requestId !== state.pimcoreEditRequestId) return;
    state.pimcoreEditObjectId = Number(payload.object?.id || objectId);
    if (!Number.isInteger(state.pimcoreEditObjectId) || state.pimcoreEditObjectId <= 0) {
      throw new Error("Pimcore zwrocil niepoprawny identyfikator obiektu.");
    }
    state.pimcoreEditMarker = String(payload.marker || "");
    state.pimcoreEditSchema = Array.isArray(payload.form_schema) ? payload.form_schema : [];
    pimcoreEditForm.dataset.pimcoreMode = "edit";
    populatePimcoreRuntimeForm(
      pimcoreEditForm,
      state.pimcoreEditSchema,
      payload.values || {},
      {
        readOnlySources: ["EAN"],
        allowRecalculate: true,
        status: pimcoreEditStatus,
        idPrefix: "pimcoreEdit",
      }
    );
    const pimcoreEditEan = pimcoreEditForm.querySelector("#pimcoreEditEan");
    if (pimcoreEditEan) pimcoreEditEan.readOnly = true;
    if (pimcoreEditObjectInfo) {
      pimcoreEditObjectInfo.textContent = [
        `ID ${state.pimcoreEditObjectId}`,
        payload.object?.path || "",
      ]
        .filter(Boolean)
        .join(" - ");
    }
    if (pimcoreEditStatus) pimcoreEditStatus.textContent = "";
    pimcoreEditSubmitButton.disabled = false;
    updatePimcoreEditSubmitState();
    if (pimcoreEditRecalculateAllButton) {
      pimcoreEditRecalculateAllButton.disabled = !pimcoreEditHasRuntimeTemplates();
    }
  } catch (error) {
    if (requestId !== state.pimcoreEditRequestId) return;
    pimcoreEditForm.textContent = "";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary-button";
    retry.textContent = "Sprobuj ponownie";
    retry.addEventListener("click", openPimcoreEditModal);
    pimcoreEditForm.appendChild(retry);
    pimcoreEditStatus.textContent = `Nie mozna pobrac danych Pimcore: ${error.message}`;
    formStatus.textContent = pimcoreEditStatus.textContent;
    if (pimcoreEditRecalculateAllButton) pimcoreEditRecalculateAllButton.disabled = true;
  } finally {
    if (requestId === state.pimcoreEditRequestId && !state.pimcoreEditObjectId) {
      pimcoreEditSubmitButton.disabled = true;
    }
    if (pimcoreEditButton) {
      pimcoreEditButton.disabled = Number(state.pimcoreExistingObject?.id || 0) <= 0;
    }
  }
}

function closePimcoreEditModal() {
  state.pimcoreEditRequestId += 1;
  pimcoreEditModal?.classList.remove("active");
  if (pimcoreEditForm) pimcoreEditForm.textContent = "";
  if (pimcoreEditStatus) pimcoreEditStatus.textContent = "";
  if (pimcoreEditRecalculateAllButton) pimcoreEditRecalculateAllButton.disabled = true;
  pimcoreEditSubmitButton?.classList.remove("pimcore-submit-blocked");
  pimcoreEditSubmitButton?.removeAttribute("aria-disabled");
  if (pimcoreEditSubmitButton) pimcoreEditSubmitButton.title = "";
  state.pimcoreEditObjectId = 0;
  state.pimcoreEditMarker = "";
  state.pimcoreEditSchema = [];
}

async function submitPimcoreRuntimeEdit(event) {
  event.preventDefault();
  if (!pimcoreEditForm.reportValidity()) return;
  if (blockPimcoreRuntimeSubmitIfNeeded(pimcoreEditForm, pimcoreEditStatus)) return;
  pimcoreEditSubmitButton.disabled = true;
  pimcoreEditStatus.textContent = "Zapisywanie i publikowanie...";
  try {
    const values = Object.fromEntries(new FormData(pimcoreEditForm).entries());
    const result = await requestJson(
      `/api/pimcore/products/${encodeURIComponent(state.pimcoreEditObjectId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ marker: state.pimcoreEditMarker, values }),
        timeoutMs: 120000,
      }
    );
    state.pimcoreEditMarker = result.marker || state.pimcoreEditMarker;
    state.pimcoreExistingObject = result.object || state.pimcoreExistingObject;
    pimcoreEditStatus.textContent = `Zapisano obiekt ${result.object?.id || state.pimcoreEditObjectId}.`;
  } catch (error) {
    pimcoreEditStatus.textContent =
      error.status === 409
        ? "Produkt zostal zmieniony w Pimcore. Zamknij okno i otworz go ponownie."
        : error.message;
  } finally {
    pimcoreEditSubmitButton.disabled = false;
  }
}

function renderSettingsPimcore() {
  const pimcore = state.settings.pimcore || {};
  const form = document.createElement("form");
  form.className = "settings-form";
  if (pimcore.setup_complete !== true) {
    form.append(settingsNote("Integracja Pimcore wymaga pierwszej konfiguracji."));
    const start = document.createElement("button");
    start.type = "button";
    start.textContent = "Uruchom kreator";
    start.addEventListener("click", openPimcoreSetupWizard);
    form.appendChild(start);
    settingsOutput.appendChild(form);
    if (state.currentUser?.role === "admin" && !state.pimcoreSetupPrompted) {
      state.pimcoreSetupPrompted = true;
      queueMicrotask(openPimcoreSetupWizard);
    }
    return;
  }
  const fields = pimcoreCompactFields(pimcore);
  const classes = pimcoreCompactClassItems(pimcore);
  const folders = pimcoreCompactFolderItems(pimcore);
  const mappings = document.createElement("div");
  const addMapping = document.createElement("button");
  const refresh = document.createElement("button");
  const advanced = document.createElement("details");
  const advancedSummary = document.createElement("summary");
  const advancedBody = document.createElement("div");
  const configuredMappings = pimcore.field_mappings?.length
    ? pimcore.field_mappings
    : [{ source: "EAN", label: "EAN", pimcore_field: pimcore.existence_fields?.[0] || "EAN", required: true }];
  mappings.className = "pimcore-simple-mapping-list wide-field";
  for (const mapping of configuredMappings) {
    mappings.appendChild(pimcoreSimpleMappingRow(mapping, fields));
  }
  addMapping.type = "button";
  addMapping.className = "secondary-button";
  addMapping.textContent = "Dodaj pole";
  addMapping.addEventListener("click", () => {
    mappings.appendChild(pimcoreSimpleMappingRow({}, fields));
  });
  refresh.type = "button";
  refresh.className = "secondary-button";
  refresh.textContent = "Odswiez klasy i foldery";
  refresh.addEventListener("click", () => {
    refreshCompactPimcoreMetadata(form, refresh);
  });
  advanced.id = "pimcoreAdvancedSettings";
  advanced.className = "pimcore-advanced-settings";
  advanced.open = false;
  advancedSummary.textContent = "Zaawansowane";
  advancedBody.className = "settings-field-group";
  advancedBody.append(
    inputField("timeout_seconds", "Timeout [s]", pimcore.timeout_seconds || 30, {
      type: "number",
      min: "1",
      max: "120",
    }),
    checkField("verify_tls", "Weryfikuj certyfikat TLS", pimcore.verify_tls !== false),
    pimcoreCsvImportButton(mappings, fields),
    settingsNote("Klucz obiektu: {EAN}. Pole wyszukiwania EAN wynika z przypisania EAN."),
    settingsNote("Typ danych wykryty automatycznie na podstawie pola Pimcore.")
  );
  advanced.append(advancedSummary, advancedBody);
  form.append(
    settingsFieldGroup(
      "Polaczenie Pimcore",
      checkField("enabled", "Integracja wlaczona", pimcore.enabled),
      inputField("base_url", "Adres Pimcore", pimcore.base_url || "", {
        placeholder: "http://twoj-adres-pimcore.example",
      }),
      credentialField("api_key", "Klucz API", pimcore.api_key_set, {
        type: "password",
        secretPath: "pimcore.api_key",
      }),
      actionRow(refresh)
    ),
    settingsFieldGroup(
      "Miejsce zapisu",
      pimcoreSetupSelect(
        "class_id",
        "Klasa produktu",
        classes,
        pimcore.class_id,
        "id",
        (item) => `${item.name} (ID ${item.id})`
      ),
      pimcoreSetupSelect(
        "parent_id",
        "Folder docelowy",
        folders,
        pimcore.parent_id,
        "id",
        (item) => `${item.path || item.key} (ID ${item.id})`
      ),
      pimcoreManualCompactLocationFields(pimcore)
    ),
    settingsFieldGroup(
      "Pola produktu",
      settingsNote("Typ danych wykryty automatycznie na podstawie pola Pimcore."),
      mappings,
      actionRow(addMapping)
    ),
    settingsFieldGroup(
      "Testy integracji",
      actionRow(
        pimcoreReadOnlyTestButton(() => collectCompactPimcoreSettings(form)),
        pimcoreOpenWriteTestButton(),
        pimcoreHistoryButton()
      ),
      pimcoreChecklistElement()
    ),
    advanced
  );
  settingsSaveButton(form, () => ({ pimcore: collectCompactPimcoreSettings(form) }));
  settingsOutput.appendChild(form);
}

function renderSettingsSlots() {
  ensureSqlColumnsDatalist();
  const form = document.createElement("form");
  form.className = "settings-form";
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent =
    "Nazwa w web jest tylko etykieta slotu. ID trafia do EAN_ID, nazwa w pliku jest zapisywana literalnie po usunieciu znakow niedozwolonych, a pole SQL sluzy do aktualizacji bazy.";
  const list = document.createElement("div");
  const addButton = document.createElement("button");
  list.className = "slot-settings-list";
  const nextPrefix = () => {
    const used = [...list.querySelectorAll('[name="prefix"]')]
      .map((input) => parseInt(input.value, 10))
      .filter((value) => Number.isFinite(value));
    const next = Math.max(0, ...used) + 1;
    return String(next).padStart(2, "0");
  };
  const addSlotRow = (slot = {}) => {
    const row = document.createElement("div");
    const remove = document.createElement("button");
    row.className = "slot-settings-row";
    row.dataset.filenameLabelExplicit = slot.filename_label_explicit ? "1" : "0";
    row.dataset.originalLabel = slot.label || "";
    row.dataset.originalFilenameLabel = slot.filename_label || slot.label || "";
    const column = inputField("sql_column", "Pole SQL", slot.sql_column || "");
    column.querySelector("input").setAttribute("list", "sqlColumnsList");
    remove.type = "button";
    remove.className = "secondary-button";
    remove.textContent = "Usun";
    remove.addEventListener("click", () => row.remove());
    row.append(
      inputField("label", "Nazwa w web", slot.label),
      inputField("prefix", "ID", slot.prefix),
      inputField("filename_label", "Nazwa w pliku", slot.filename_label || slot.label),
      column,
      remove
    );
    list.appendChild(row);
  };
  for (const slot of state.settings.slots || []) {
    addSlotRow(slot);
  }
  addButton.type = "button";
  addButton.className = "secondary-button";
  addButton.textContent = "Dodaj slot";
  addButton.addEventListener("click", () => {
    const prefix = nextPrefix();
    addSlotRow({
      prefix,
      label: `Slot ${prefix}`,
      filename_label: `Slot ${prefix}`,
      filename_label_explicit: true,
      sql_column: "",
    });
  });
  form.append(settingsFieldGroup("Lista slotow", note, list, actionRow(addButton, detectSqlColumnsButton())));
  settingsSaveButton(form, () => {
    const slots = [...form.querySelectorAll(".slot-settings-row")].map((row) => {
      const label = row.querySelector('[name="label"]').value;
      const filenameLabel = row.querySelector('[name="filename_label"]').value;
      const wasExplicit = row.dataset.filenameLabelExplicit === "1";
      const originalLabel = row.dataset.originalLabel || "";
      const originalFilenameLabel = row.dataset.originalFilenameLabel || "";
      const unchangedLegacyFilename =
        !wasExplicit && label === originalLabel && filenameLabel === originalFilenameLabel;
      return {
        prefix: row.querySelector('[name="prefix"]').value,
        label,
        filename_label: unchangedLegacyFilename ? "" : filenameLabel,
        sql_column: row.querySelector('[name="sql_column"]').value,
      };
    });
    return { slots };
  });
  settingsOutput.appendChild(form);
}

function renderSettingsUsers() {
  const wrapper = document.createElement("div");
  wrapper.className = "settings-form";
  const addForm = document.createElement("form");
  addForm.className = "user-add-form wide-field";
  const input = document.createElement("input");
  const password = document.createElement("input");
  const role = document.createElement("select");
  const button = document.createElement("button");
  input.name = "username";
  input.placeholder = "Nowy uzytkownik";
  password.name = "password";
  password.type = "password";
  password.placeholder = "Haslo";
  for (const value of ["user", "admin"]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    role.appendChild(option);
  }
  button.textContent = "Dodaj";
  addForm.append(input, password, role, button);
  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = await requestJson("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: input.value, password: password.value, role: role.value }),
    });
    state.settings.users = payload.users;
    state.currentUser = payload.current_user || state.currentUser;
    updateAdminUi();
    input.value = "";
    password.value = "";
    renderSettings();
  });
  const list = document.createElement("div");
  list.className = "user-list";
  for (const user of state.settings.users || []) {
    const row = document.createElement("div");
    row.className = "user-row";
    row.classList.toggle("user-row-locked", Boolean(user.locked));
    const name = document.createElement("div");
    const nameTitle = document.createElement("strong");
    const nameMeta = document.createElement("small");
    const role = document.createElement("select");
    const enabled = document.createElement("input");
    const enabledWrap = document.createElement("div");
    const enabledText = document.createElement("div");
    const enabledTitle = document.createElement("strong");
    const enabledDescription = document.createElement("small");
    const passwordInput = document.createElement("input");
    const actions = document.createElement("div");
    const save = document.createElement("button");
    const unlock = document.createElement("button");
    const revokeSessions = document.createElement("button");
    const revokeExtension = document.createElement("button");
    const isCurrentUser =
      state.currentUser &&
      String(state.currentUser.username || "").toLowerCase() === String(user.username || "").toLowerCase();
    const loginMeta = [];
    name.className = "user-summary";
    nameTitle.textContent = user.username;
    if (user.locked) {
      loginMeta.push(
        user.lock_manual
          ? "Zablokowane do recznego odblokowania"
          : `Zablokowane do ${user.lock_expires_at || "-"}`
      );
    }
    if (user.failed_login_count) {
      loginMeta.push(`Bledne proby: ${user.failed_login_count}`);
    }
    if (user.last_failed_login_at) {
      const ip = user.last_failed_login_ip ? `, ${user.last_failed_login_ip}` : "";
      loginMeta.push(`Ostatnia bledna: ${user.last_failed_login_at}${ip}`);
    }
    loginMeta.push(`Sesje v${Number(user.session_version || 0)}`);
    loginMeta.push(
      `Token rozszerzenia v${Number(user.extension_token_version || 0)}${
        user.extension_token_last_used_at ? `, ostatnio ${user.extension_token_last_used_at}` : ""
      }`
    );
    nameMeta.textContent = loginMeta.join(" | ") || "Brak blednych prob logowania.";
    nameMeta.className = user.locked ? "user-lock-warning" : "";
    name.append(nameTitle, nameMeta);
    for (const value of ["user", "admin"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = user.role === value;
      role.appendChild(option);
    }
    enabled.type = "checkbox";
    enabled.checked = Boolean(user.enabled);
    enabled.disabled = Boolean(isCurrentUser);
    enabled.setAttribute("aria-label", `Konto aktywne: ${user.username}`);
    enabledTitle.textContent = "Konto aktywne";
    enabledDescription.textContent = isCurrentUser
      ? "Nie mozna wylaczyc konta aktualnej sesji."
      : "Wylaczenie blokuje logowanie tego uzytkownika.";
    enabledText.append(enabledTitle, enabledDescription);
    enabledWrap.className = "check-row compact-check";
    enabledWrap.append(enabled, enabledText);
    passwordInput.type = "password";
    passwordInput.placeholder = user.has_password ? "Nowe haslo opcjonalnie" : "Ustaw haslo";
    save.type = "button";
    save.textContent = "Zapisz";
    unlock.type = "button";
    unlock.textContent = "Odblokuj";
    unlock.hidden = !user.locked && !user.failed_login_count;
    revokeSessions.type = "button";
    revokeSessions.textContent = "Wyloguj sesje";
    revokeExtension.type = "button";
    revokeExtension.textContent = "Uniewaznij token";
    actions.className = "user-actions";
    save.addEventListener("click", async () => {
      const payload = { enabled: enabled.checked, role: role.value };
      if (passwordInput.value) {
        payload.password = passwordInput.value;
      }
      const response = await requestJson(`/api/users/${encodeURIComponent(user.username)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.settings.users = response.users;
      state.currentUser = response.current_user || state.currentUser;
      updateAdminUi();
      renderSettings();
    });
    unlock.addEventListener("click", async () => {
      const response = await requestJson(`/api/users/${encodeURIComponent(user.username)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unlock: true }),
      });
      state.settings.users = response.users;
      state.currentUser = response.current_user || state.currentUser;
      if (response.session_invalidated) {
        window.location.href = "/login";
        return;
      }
      updateAdminUi();
      renderSettings();
    });
    revokeSessions.addEventListener("click", async () => {
      const response = await requestJson(`/api/users/${encodeURIComponent(user.username)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revoke_sessions: true }),
      });
      if (response.session_invalidated) {
        window.location.href = "/login";
        return;
      }
      state.settings.users = response.users;
      state.currentUser = response.current_user || state.currentUser;
      updateAdminUi();
      renderSettings();
    });
    revokeExtension.addEventListener("click", async () => {
      const response = await requestJson(`/api/users/${encodeURIComponent(user.username)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revoke_extension_token: true }),
      });
      state.settings.users = response.users;
      state.currentUser = response.current_user || state.currentUser;
      updateAdminUi();
      renderSettings();
    });
    actions.append(save, unlock, revokeSessions, revokeExtension);
    row.append(name, role, passwordInput, enabledWrap, actions);
    list.appendChild(row);
  }
  wrapper.append(
    settingsFieldGroup("Nowy uzytkownik", addForm),
    settingsFieldGroup("Lista uzytkownikow", list)
  );
  settingsOutput.appendChild(wrapper);
}

function renderSettings() {
  if (!state.settings) {
    return;
  }
  settingsOutput.textContent = "";
  document.querySelectorAll(".settings-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.settingsTab === state.activeSettingsTab);
  });
  settingsStatus.textContent = state.settings.windows_admin
    ? "Proces backendu ma uprawnienia administratora Windows. Rola web admin jest niezalezna."
    : "Proces backendu dziala bez uprawnien administratora Windows. Rola web admin jest niezalezna.";
  if (state.activeSettingsTab === "app") renderSettingsApp();
  if (state.activeSettingsTab === "processing") renderSettingsProcessing();
  if (state.activeSettingsTab === "security") renderSettingsSecurity();
  if (state.activeSettingsTab === "ftp") renderSettingsFtp();
  if (state.activeSettingsTab === "sql") renderSettingsSql();
  if (state.activeSettingsTab === "pimcore") renderSettingsPimcore();
  if (state.activeSettingsTab === "slots") renderSettingsSlots();
  if (state.activeSettingsTab === "users") renderSettingsUsers();
}

async function loadSettings() {
  state.settings = await requestJson("/api/settings");
  state.settingsSecrets = null;
  state.currentUser = state.settings.current_user || state.currentUser;
  state.defaultSlotFit = Boolean(state.settings.auto_content_fit);
  state.ftpEnabled = state.settings.ftp?.enabled !== false;
  state.processing = state.settings.processing || state.processing || {};
  state.security = state.settings.security || state.security || {};
  state.productFields = state.settings.product_fields || state.productFields || {};
  updateAdminUi();
  applyTimingDetailsVisibility();
  applyProductFieldLabels();
  renderSettings();
}

document.querySelectorAll("[data-modal]").forEach((button) => {
  button.addEventListener("click", () => openModal(button.dataset.modal));
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", closeModals);
});

document.querySelectorAll("[data-close-web-images]").forEach((button) => {
  button.addEventListener("click", closeWebImagesModal);
});

document.querySelectorAll("[data-close-history-detail]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#historyDetailModal")?.classList.remove("active");
  });
});

document.querySelectorAll("[data-close-history-timing]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#historyTimingModal")?.classList.remove("active");
  });
});

document.querySelectorAll("[data-close-backup-history]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#backupHistoryModal")?.classList.remove("active");
  });
});

document.querySelectorAll("[data-close-backup-diff]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#backupDiffModal")?.classList.remove("active");
  });
});

document.querySelectorAll("[data-close-logs-clear]").forEach((button) => {
  button.addEventListener("click", closeLogsClearModal);
});

document.querySelectorAll("[data-close-secret-reveal]").forEach((button) => {
  button.addEventListener("click", () => closeSecretRevealModal());
});

document.querySelectorAll("[data-close-process-alert]").forEach((button) => {
  button.addEventListener("click", closeProcessAlert);
});

pimcoreTestSubmitButton?.addEventListener("click", () => {
  submitPimcoreWriteTest().catch((error) => {
    if (pimcoreTestStatus) {
      pimcoreTestStatus.textContent = error.message;
    }
    if (pimcoreTestSubmitButton) {
      pimcoreTestSubmitButton.disabled = false;
    }
    if (pimcoreTestClearButton) {
      pimcoreTestClearButton.disabled = false;
    }
    if (pimcoreTestRegenerateButton) {
      pimcoreTestRegenerateButton.disabled = false;
    }
  });
});

pimcoreTestClearButton?.addEventListener("click", () => {
  if (state.pimcoreTestOperation?.active) return;
  pimcoreTestForm.reset();
  pimcoreTestModal.querySelectorAll('[name="pimcore_cleanup_policy"]').forEach((item) => {
    item.checked = false;
  });
  clearPimcoreLiveLog();
});

pimcoreTestCloseButton?.addEventListener("click", () => {
  if (pimcoreTestModal) {
    pimcoreTestModal.classList.remove("active");
  }
});

pimcoreTestRegenerateButton?.addEventListener("click", () => {
  if (state.pimcoreTestOperation?.active) return;
  clearPimcoreLiveLog();
  loadPimcoreTestSample();
});

pimcoreTemplateTranslate?.addEventListener("change", () => {
  pimcoreTemplateLanguage.disabled = !pimcoreTemplateTranslate.checked;
  if (pimcoreTemplateTranslate.checked) {
    if (!pimcoreTemplateLanguage.value.trim()) {
      pimcoreTemplateLanguage.value = pimcoreTemplateLanguageForRow(state.pimcoreTemplateRow);
    }
    pimcoreTemplateLanguage.focus();
  }
});

pimcoreTemplatePreviewButton?.addEventListener("click", previewPimcoreTemplate);
pimcoreTemplateSaveButton?.addEventListener("click", savePimcoreTemplateBuilder);
pimcoreTemplateClearButton?.addEventListener("click", () => {
  pimcoreTemplateText.value = "";
  const sqlQuery = pimcoreTemplateSqlControls?.querySelector('[name="mapping_sql_query"]');
  const sqlProfile = pimcoreTemplateSqlControls?.querySelector('[name="mapping_sql_profile_id"]');
  if (sqlQuery) sqlQuery.value = "";
  if (sqlProfile) sqlProfile.value = "";
  pimcoreTemplateTranslate.checked = false;
  pimcoreTemplateLanguage.value = "";
  pimcoreTemplateLanguage.disabled = true;
  savePimcoreTemplateBuilder();
});
pimcoreTemplateCancelButton?.addEventListener("click", closePimcoreTemplateBuilder);

pimcoreHistoryCloseButton?.addEventListener("click", () => {
  if (pimcoreHistoryModal) {
    pimcoreHistoryModal.classList.remove("active");
  }
});

pimcoreHistoryFilters?.addEventListener("submit", (event) => {
  event.preventDefault();
  loadPimcoreHistory().catch((error) => {
    if (pimcoreHistoryOutput) {
      pimcoreHistoryOutput.className = "history-output empty-state";
      pimcoreHistoryOutput.textContent = error.message;
    }
  });
});

pimcoreHistoryExportCsvButton?.addEventListener("click", () => exportPimcoreSubmissions("csv"));
pimcoreHistoryExportJsonButton?.addEventListener("click", () => exportPimcoreSubmissions("json"));

pimcoreMissingCreateButton?.addEventListener("click", () => {
  openPimcoreCreateModal(state.pimcoreMissingEan);
});

pimcoreMissingContinueButton?.addEventListener("click", () => {
  pimcoreMissingModal?.classList.remove("active");
});

pimcoreMissingCancelButton?.addEventListener("click", () => {
  pimcoreMissingModal?.classList.remove("active");
});

pimcoreCreateCancelButton?.addEventListener("click", () => {
  pimcoreCreateModal?.classList.remove("active");
});

pimcoreCreateForm?.addEventListener("submit", submitPimcoreRuntimeCreate);

pimcoreEditButton?.addEventListener("click", openPimcoreEditModal);
pimcoreEditForm?.addEventListener("submit", submitPimcoreRuntimeEdit);
pimcoreEditRecalculateAllButton?.addEventListener("click", recalculateAllPimcoreEditFields);
pimcoreEditCancelButton?.addEventListener("click", () => {
  closePimcoreEditModal();
});

pimcoreSetupNextButton?.addEventListener("click", advancePimcoreSetup);
pimcoreSetupBackButton?.addEventListener("click", () => {
  capturePimcoreSetupStep();
  if (!state.pimcoreSetup) return;
  state.pimcoreSetup.step = Math.max(1, state.pimcoreSetup.step - 1);
  renderPimcoreSetupStep();
});
pimcoreSetupCancelButton?.addEventListener("click", () => {
  pimcoreSetupModal?.classList.remove("active");
  state.pimcoreSetup = null;
});

processAlertLoadButton?.addEventListener("click", () => {
  const jobId = processAlertLoadButton.dataset.jobId || "";
  const job = state.processJobs.get(jobId);
  if (!job) {
    closeProcessAlert();
    return;
  }
  if (hasPendingUserChanges() && !window.confirm("Wczytac wpis z zadania i zastapic aktualny formularz?")) {
    return;
  }
  const entry = entryFromProcessJob(job);
  fillForm(entry, { loadPhotos: Boolean(entry.product_id || entry.ean) });
  closeProcessAlert();
});

activeUsersMoreButton?.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleActiveUsersPopover();
});

document.addEventListener("click", (event) => {
  if (!activeUsersPresence || activeUsersPresence.contains(event.target)) {
    return;
  }
  toggleActiveUsersPopover(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    toggleActiveUsersPopover(false);
  }
});

themeToggleButton?.addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  applyTheme();
});

document.querySelectorAll(".settings-tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.activeSettingsTab = button.dataset.settingsTab;
    renderSettings();
  });
});

historyUserFilter?.addEventListener("change", () => {
  state.historyPage = 1;
  loadHistory({ page: 1 }).catch(showHistoryLoadError);
});

historySearchInput?.addEventListener("input", () => {
  window.clearTimeout(state.historySearchTimer);
  state.historySearchTimer = window.setTimeout(() => {
    state.historyPage = 1;
    loadHistory({ page: 1 }).catch(showHistoryLoadError);
  }, 250);
});

historyRefreshButton?.addEventListener("click", () => {
  loadHistory({ page: state.historyPage || 1 }).catch(showHistoryLoadError);
});

historyPrevButton?.addEventListener("click", () => {
  const page = Math.max(1, Number(state.historyPage || 1) - 1);
  loadHistory({ page }).catch(showHistoryLoadError);
});

historyNextButton?.addEventListener("click", () => {
  const page = Math.max(1, Number(state.historyPage || 1) + 1);
  loadHistory({ page }).catch(showHistoryLoadError);
});

logsRefreshButton?.addEventListener("click", () => {
  loadLogs().catch((error) => {
    logsOutput.textContent = error.message;
  });
});

logsClearButton?.addEventListener("click", () => {
  openLogsClearModal();
});

logsClearForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  clearLogs(logsClearPassword.value).catch((error) => {
    if (logsClearStatus) {
      logsClearStatus.textContent = error.message;
    }
  });
});

secretRevealForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const password = secretRevealPassword?.value || "";
  if (!password) {
    if (secretRevealStatus) {
      secretRevealStatus.textContent = "Podaj haslo administratora.";
    }
    return;
  }
  closeSecretRevealModal(password);
});

entrySelect.addEventListener("change", () => {
  const option = entrySelect.selectedOptions[0];
  if (!option || !option.dataset.entry) return;
  fillForm(JSON.parse(option.dataset.entry), { loadPhotos: true });
});

for (const name of ["name", "type_name", "model"]) {
  productForm.elements[name].addEventListener("input", scheduleProductAutoSearch);
}

productForm.elements.ean?.addEventListener("input", handlePimcoreEanInput);

for (const name of trackedProductFields) {
  productForm.elements[name]?.addEventListener("input", () => scheduleBackgroundFtpLookup());
}

for (const name of Object.keys(fieldListKey)) {
  productForm.elements[name]?.addEventListener("change", () => {
    promptAddProductFieldToList(name).catch((error) => {
      formStatus.textContent = error.message;
    });
  });
}

productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearResult();
  try {
    ensureSlotUploadsReady();
    setBusy(true, "Sprawdzanie list...");
    await ensureProductListValues();
    const identityChanged = productFieldsChangedSinceLoad();
    const updateMode = hasPendingUserChanges();
    setBusy(
      true,
      updateMode
        ? identityChanged
          ? "Aktualizowanie i przenoszenie istniejacych zdjec..."
          : "Aktualizowanie..."
        : "Synchronizowanie brakujacych danych..."
    );
    const changedPrefixes = pendingChangedSlotPrefixes();
    const data = new FormData(productForm);
    for (const slot of state.slots || []) {
      data.delete(`slot_${slot.prefix}`);
    }
    for (const [prefix, item] of state.files.entries()) {
      const token = slotFileToken(item);
      if (token) {
        data.set(`existing_slot_${prefix}`, token);
        data.set(`existing_slot_name_${prefix}`, slotFileName(item));
        if (item.preprocessed) {
          data.set(`existing_slot_preprocessed_${prefix}`, "1");
        }
      } else {
        const file = slotFileObject(item);
        if (!file) {
          throw new Error(`Slot ${prefix} nie ma pliku ani tokenu cache.`);
        }
        data.set(`slot_${prefix}`, file, file.name);
      }
      data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
    }
    for (const [prefix, photo] of state.loadedPhotos.entries()) {
      if (!state.files.has(prefix) && photo.dirty) {
        const transferSource = transferableSlotSource(prefix, photo);
        const token = transferablePhotoToken(photo, prefix);
        if (token) {
          data.set(`existing_slot_${prefix}`, token);
          data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
          changedPrefixes.add(prefix);
        } else if (transferSource === "ftp" && photo.ftp_filename) {
          data.set(`existing_ftp_slot_${prefix}`, photo.ftp_filename);
          data.set(
            `existing_ftp_ean_${prefix}`,
            photo.ean || state.loadedEntryOriginal?.ean || productForm.elements.ean.value
          );
          data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
          changedPrefixes.add(prefix);
        } else if (photo.dirty) {
          throw new Error(`Slot ${prefix} nie ma lokalnego ani FTP zrodla do przeniesienia.`);
        }
      }
    }
    for (const [prefix, item] of state.deletedSlots.entries()) {
      data.set(`delete_slot_${prefix}`, "1");
      if (item.token) data.set(`delete_local_slot_${prefix}`, item.token);
      if (item.ftp_filename) data.set(`delete_ftp_slot_${prefix}`, item.ftp_filename);
      if (item.sql) data.set(`delete_sql_slot_${prefix}`, "1");
    }
    startProcessStatusTicker(updateMode ? "Aktualizacja" : "Synchronizacja", changedPrefixes);
    const payload = await requestJson("/api/process/background", { method: "POST", body: data });
    const job = payload.job || {};
    stopProcessStatusTicker("Backend przyjal zadanie w tle.");
    trackProcessJob(job);
    refreshProcessQueue().catch(() => {});
    showQueuedProcess(job);
    resetCurrentDraft({
      clearOutput: false,
      status: "Zadanie przyjete w tle. Mozesz uzupelniac kolejny wpis.",
    });
    setBusy(false, "Zadanie przyjete w tle. Mozesz uzupelniac kolejny wpis.");
  } catch (error) {
    stopProcessStatusTicker();
    showError(error);
    setBusy(false, "");
  }
});

function resetCurrentDraft({ clearOutput = true, status = "" } = {}) {
  state.photoLoadRequestId += 1;
  productForm.reset();
  productForm.elements.product_id.value = "";
  for (const prefix of Array.from(state.filePreviewUrls.keys())) {
    revokeFilePreviewUrl(prefix);
  }
  state.files.clear();
  state.loadedPhotos.clear();
  state.slotFits.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  state.userSelectedSlotSources.clear();
  state.photoSourceStatus.clear();
  state.ftpPreviewLoading.clear();
  state.ftpPreviewBackgroundLoading.clear();
  state.photoSourcesLoaded.clear();
  state.backgroundFtpLookupKey = "";
  state.backgroundFtpLookupRequestId += 1;
  window.clearTimeout(state.pimcoreLookupTimer);
  state.pimcoreLookupRequestId += 1;
  state.pimcoreLastCheckedEan = "";
  state.pimcoreMissingEan = "";
  state.pimcoreCreateSchema = [];
  state.pimcoreExistingObject = null;
  if (pimcoreEditButton) pimcoreEditButton.disabled = true;
  pimcoreMissingModal?.classList.remove("active");
  pimcoreCreateModal?.classList.remove("active");
  closePimcoreEditModal();
  window.clearTimeout(state.backgroundFtpLookupTimer);
  window.clearTimeout(state.backgroundFtpPreviewTimer);
  state.loadedEntryOriginal = null;
  state.lastAutoSearchKey = "";
  applyProductFieldSettings();
  renderSlots();
  renderEntrySelect();
  updateFieldWarnings();
  if (clearOutput) {
    clearResult();
  }
  formStatus.textContent = status;
}

clearButton.addEventListener("click", () => {
  resetCurrentDraft();
});

findByEanButton.addEventListener("click", () => {
  searchByEan().catch((error) => {
    formStatus.textContent = error.message;
  });
});

findProductButton.addEventListener("click", () => {
  searchByProduct().catch((error) => {
    formStatus.textContent = error.message;
  });
});

scanWebImagesButton?.addEventListener("click", () => {
  scanWebImages().catch((error) => {
    formStatus.textContent = error.message;
  });
});

webImagesButton?.addEventListener("click", () => {
  openWebImagesModal();
  renderWebImagesPicker();
});

webImageUrl?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  scanWebImages().catch((error) => {
    formStatus.textContent = error.message;
  });
});

for (const input of [
  webImageMinWidth,
  webImageMinHeight,
  webImageMinKb,
  webImageUrlFilter,
  webImageHideThumbnails,
]) {
  input?.addEventListener("input", renderWebImagesPicker);
  input?.addEventListener("change", renderWebImagesPicker);
}

if (webImageScanMode) {
  webImageScanMode.value = state.webImageScanMode;
}

webImageScanMode?.addEventListener("change", () => {
  state.webImageScanMode = webImageScanMode.value || "links";
  localStorage.setItem("picorg-web-image-scan-mode", state.webImageScanMode);
  renderWebImagesPicker();
});

browserExtensionHelpButton?.addEventListener("click", () => {
  if (!browserExtensionHelp) return;
  browserExtensionHelp.hidden = !browserExtensionHelp.hidden;
});

browserExtensionDownload?.addEventListener("click", () => {
  downloadBrowserExtension().catch((error) => {
    formStatus.textContent = error.message;
  });
});

browserExtensionReceiveButton?.addEventListener("click", () => {
  receiveBrowserExtensionImages().catch((error) => {
    formStatus.textContent = error.message;
  });
});

webImagesSelectVisibleButton?.addEventListener("click", () => {
  for (const entry of visibleWebImageEntries()) {
    state.webImageSelected.add(entry.index);
    queueWebImageCache(entry.image, "web", { render: false });
  }
  renderWebImagesPicker();
});

webImagesClearSelectionButton?.addEventListener("click", () => {
  state.webImageSelected.clear();
  renderWebImagesPicker();
});

webImagesClearDataButton?.addEventListener("click", () => {
  clearLoadedWebImages();
});

webImagesAddButton?.addEventListener("click", () => {
  addSelectedWebImagesToSlots().catch((error) => {
    formStatus.textContent = error.message;
  });
});

listAddForm.addEventListener("submit", (event) => {
  addListValue(event).catch((error) => {
    listStatus.textContent = error.message;
  });
});

listAddInput.addEventListener("input", () => {
  state.listFilter = listAddInput.value;
  renderListEditor();
  listAddInput.focus();
  const length = listAddInput.value.length;
  listAddInput.setSelectionRange(length, length);
});

logoutButton.addEventListener("click", async () => {
  if (!confirmPageExit()) {
    return;
  }
  state.navigationGuardBypass = true;
  await fetch("/api/logout", {
    method: "POST",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      [CLIENT_ID_HEADER]: activePresenceClientId(),
      ...(state.csrfToken ? { [CSRF_HEADER]: state.csrfToken } : {}),
    },
  }).catch(() => {});
  window.location.href = "/";
});

setupAutocomplete();
setupFieldChangeTracking();
setupPageExitGuards();
applyTheme();
loadBootstrap().catch(showError);
startBackgroundPollers();
