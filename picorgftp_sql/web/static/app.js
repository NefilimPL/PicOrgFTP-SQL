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
  logs: null,
  theme: localStorage.getItem("picorg-theme") || "light",
  suppressAutoSearch: false,
  lastAutoSearchKey: "",
  photoLoadRequestId: 0,
  photoSourceStatus: new Map(),
  listFilter: "",
};

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

const slotGrid = document.querySelector("#slotGrid");
const slotTemplate = document.querySelector("#slotTemplate");
const productForm = document.querySelector("#productForm");
const formStatus = document.querySelector("#formStatus");
const resultOutput = document.querySelector("#resultOutput");
const resultMeta = document.querySelector("#resultMeta");
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
const saveEntryButton = document.querySelector("#saveEntryButton");
const listTabs = document.querySelector("#listTabs");
const listValues = document.querySelector("#listValues");
const listAddForm = document.querySelector("#listAddForm");
const listAddInput = document.querySelector("#listAddInput");
const listStatus = document.querySelector("#listStatus");
const settingsOutput = document.querySelector("#settingsOutput");
const settingsStatus = document.querySelector("#settingsStatus");
const entryMatches = document.querySelector("#entryMatches");
const historyUserFilter = document.querySelector("#historyUserFilter");
const historyRefreshButton = document.querySelector("#historyRefreshButton");
const historyOutput = document.querySelector("#historyOutput");
const historyDetailTitle = document.querySelector("#historyDetailTitle");
const historyDetailOutput = document.querySelector("#historyDetailOutput");
const logsRefreshButton = document.querySelector("#logsRefreshButton");
const logsOutput = document.querySelector("#logsOutput");

async function requestJson(path, options = {}) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new Error(
      `Nie udalo sie polaczyc z backendem (${path}). Sprawdz, czy serwer web dziala. Szczegoly: ${
        error.message || error
      }`
    );
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = "/login";
    }
    throw new Error(payload.detail || "Operacja nie powiodla sie.");
  }
  return payload;
}

function updateAdminUi() {
  state.isAdmin = state.currentUser?.role === "admin";
  document.querySelectorAll(".admin-only").forEach((node) => {
    node.style.display = state.isAdmin ? "" : "none";
  });
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
    loadHistory().catch((error) => {
      historyOutput.textContent = error.message;
    });
  }
  if (name === "logs") {
    loadLogs().catch((error) => {
      logsOutput.textContent = error.message;
    });
  }
}

function closeModals() {
  document.querySelectorAll(".modal-view").forEach((modal) => modal.classList.remove("active"));
  setActiveModalNav("");
}

function fileLabel(file) {
  if (!file) {
    return "Brak pliku";
  }
  const kb = Math.max(1, Math.round(file.size / 1024));
  return `${file.name} (${kb} KB)`;
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

function uniqueValues(values, limit = 200) {
  const seen = new Set();
  const result = [];
  for (const value of values || []) {
    const text = String(value || "").trim();
    if (!text) continue;
    const key = text.toUpperCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(text);
    if (result.length >= limit) break;
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

function renderAutocompletePanel(input, panel, values) {
  if (activeAutocompletePanel && activeAutocompletePanel !== panel && document.activeElement !== input) {
    return;
  }
  closeAutocompletePanels(panel);
  const typed = input.value.trim().toUpperCase();
  const filtered = values.filter((value) => !typed || value.toUpperCase().includes(typed)).slice(0, 200);
  panel.textContent = "";
  if (!filtered.length) {
    panel.classList.remove("active");
    return;
  }
  for (const value of filtered) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = value;
    button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      closeAutocompletePanels();
    });
    panel.appendChild(button);
  }
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
              renderAutocompletePanel(input, panel, uniqueValues([...values, ...local]));
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
      if (event.key === "Escape") closeAutocompletePanels();
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
}

function setupFieldChangeTracking() {
  for (const fieldName of trackedProductFields) {
    productForm.elements[fieldName]?.addEventListener("input", updateFieldWarnings);
  }
}

function defaultSlotSource(photo) {
  if (photo?.local && photo?.token) return "local";
  if (photo?.sql && sqlLinkFromPhoto(photo)) return "sql";
  if (photo?.ftp && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  return "";
}

function selectedSlotSource(prefix, photo) {
  const selected = state.slotSources.get(prefix);
  if (selected === "local" && photo?.token) return "local";
  if (selected === "ftp" && (photo?.ftp_token || photo?.ftp_filename)) return "ftp";
  if (selected === "sql" && sqlLinkFromPhoto(photo)) return "sql";
  return defaultSlotSource(photo);
}

function selectedPhotoToken(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  if (source === "ftp") return photo?.ftp_token || "";
  if (source === "sql") return "";
  return photo?.token || "";
}

function isHttpUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (_error) {
    return false;
  }
}

function sqlLinkFromPhoto(photo) {
  const value = String(photo?.sql_value || "").trim();
  return isHttpUrl(value) ? value : "";
}

function revokeFilePreviewUrl(prefix) {
  const url = state.filePreviewUrls.get(prefix);
  if (url) URL.revokeObjectURL(url);
  state.filePreviewUrls.delete(prefix);
}

function filePreviewUrl(prefix, file) {
  const current = state.filePreviewUrls.get(prefix);
  if (current) return current;
  const url = URL.createObjectURL(file);
  state.filePreviewUrls.set(prefix, url);
  return url;
}

function isFileImageLike(file) {
  const name = String(file?.name || "").toLowerCase();
  return (
    String(file?.type || "").startsWith("image/") ||
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
  if (selectedSlotSource(prefix, photo) === "sql") {
    return sqlLinkFromPhoto(photo);
  }
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
  if (photo.sql_value) {
    return `SQL: ${photo.sql_value}`;
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
    await navigator.clipboard.writeText(text);
  } else {
    const field = document.createElement("textarea");
    field.value = text;
    field.style.position = "fixed";
    field.style.left = "-9999px";
    document.body.appendChild(field);
    field.focus();
    field.select();
    document.execCommand("copy");
    field.remove();
  }
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
    const canPreview =
      (key === "local" && photo?.token) ||
      (key === "ftp" && photo?.ftp_filename) ||
      (key === "sql" && sqlLinkFromPhoto(photo));
    const badge = document.createElement(canPreview ? "button" : "span");
    const selected = selectedSlotSource(prefix, photo) === key;
    badge.dataset.source = key;
    badge.className = `slot-badge slot-badge-${key} ${photo && photo[key] ? "on" : ""} ${
      selected ? "selected" : ""
    }`;
    badge.title = selected ? `${title} (aktywny podglad)` : title;
    badge.textContent = label;
    if (canPreview) {
      badge.type = "button";
      badge.setAttribute("aria-pressed", selected ? "true" : "false");
      badge.addEventListener("click", (event) => {
        event.stopPropagation();
        state.slotSources.set(prefix, key);
        if (key === "ftp" && !photo.ftp_token) {
          loadFtpPreview(photo, prefix).catch((error) => {
            formStatus.textContent = error.message;
          });
        } else {
          updateSlotPreview(prefix);
        }
      });
    }
    badges.appendChild(badge);
  }
  const sqlLink = sqlLinkFromPhoto(photo);
  if (sqlLink) {
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "slot-badge slot-badge-link on";
    copy.textContent = "LINK";
    copy.title = "Kopiuj link www z SQL";
    copy.addEventListener("click", (event) => {
      event.stopPropagation();
      copyTextToClipboard(sqlLink, "Skopiowano link SQL.").catch((error) => {
        formStatus.textContent = error.message || "Nie udalo sie skopiowac linku.";
      });
    });
    badges.appendChild(copy);
  }
  container.appendChild(badges);
}

async function loadFtpPreview(photo, prefix, requestId = state.photoLoadRequestId) {
  if (!photo?.ftp_filename) return;
  const payload = await requestJson("/api/ftp-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ean: formValue("ean") || photo.ean || "", filename: photo.ftp_filename }),
  });
  const updated = {
    ...photo,
    ftp_token: payload.token || "",
    ftp_url: payload.url || "",
    ftp_thumb_url: payload.thumb_url || "",
  };
  if (requestId !== state.photoLoadRequestId) {
    return;
  }
  state.loadedPhotos.set(prefix, updated);
  state.slotSources.set(prefix, "ftp");
  updateSlotPreview(prefix);
}

function isSlotFit(prefix) {
  if (state.slotFits.has(prefix)) {
    return Boolean(state.slotFits.get(prefix));
  }
  return Boolean(state.defaultSlotFit);
}

function thumbnailUrl(photo, prefix) {
  const source = selectedSlotSource(prefix, photo);
  if (source === "sql") {
    return sqlLinkFromPhoto(photo);
  }
  const url =
    source === "ftp"
      ? photo?.ftp_thumb_url || photo?.ftp_url || ""
      : photo?.thumb_url || photo?.url || "";
  if (!url) return "";
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}fit=${isSlotFit(prefix) ? "1" : "0"}&width=260&height=180`;
}

function clearSlotAssignment(prefix, options = {}) {
  const markDelete = options.markDelete !== false;
  if (markDelete) {
    markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  }
  revokeFilePreviewUrl(prefix);
  state.files.delete(prefix);
  state.loadedPhotos.delete(prefix);
  state.slotFits.delete(prefix);
  state.slotSources.delete(prefix);
}

function setSlotFile(prefix, file) {
  markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  revokeFilePreviewUrl(prefix);
  state.files.set(prefix, file);
  state.loadedPhotos.delete(prefix);
  state.slotSources.delete(prefix);
}

function getSlotAssignment(prefix) {
  if (state.files.has(prefix)) {
    return { type: "file", prefix, value: state.files.get(prefix), source: state.slotSources.get(prefix) || "" };
  }
  if (state.loadedPhotos.has(prefix)) {
    return { type: "loaded", prefix, value: state.loadedPhotos.get(prefix), source: state.slotSources.get(prefix) || "" };
  }
  return null;
}

function setSlotAssignment(prefix, assignment) {
  const sourceFit = assignment ? isSlotFit(assignment.prefix || prefix) : false;
  const sourceType = assignment?.source || "";
  clearSlotAssignment(prefix);
  if (!assignment) {
    return;
  }
  if (assignment.type === "file") {
    state.files.set(prefix, assignment.value);
    state.slotFits.set(prefix, sourceFit);
    if (sourceType) state.slotSources.set(prefix, sourceType);
    return;
  }
  if (assignment.type === "loaded") {
    state.loadedPhotos.set(prefix, { ...assignment.value, prefix, dirty: true });
    state.slotFits.set(prefix, sourceFit);
    if (sourceType) state.slotSources.set(prefix, sourceType);
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
  setSlotAssignment(targetPrefix, source);
  clearSlotAssignment(sourcePrefix);
  formStatus.textContent = `Przeniesiono slot ${sourcePrefix} -> ${targetPrefix}.`;
  renderSlots();
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
    badge.classList.toggle("selected", selected);
    badge.setAttribute("aria-pressed", selected ? "true" : "false");
  });
  if (fitButton) {
    fitButton.classList.toggle("active", isSlotFit(prefix));
  }
  preview.classList.remove("has-image", "thumb-loading", "loaded-photo");
  previewImage.removeAttribute("src");
  empty.textContent = "Brak pliku";
  if (selectedFile) {
    if (isFileImageLike(selectedFile)) {
      renderSelectedFilePreview(prefix, selectedFile, preview, previewImage, empty);
    } else {
      empty.textContent = selectedFile.name;
    }
    return;
  }
  if (!loadedPhoto) return;
  preview.classList.add("loaded-photo");
  const thumb = thumbnailUrl(loadedPhoto, prefix);
  if (thumb && (loadedPhoto.is_image || selectedSlotSource(prefix, loadedPhoto) === "sql")) {
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

function renderSlots(slots = state.slots) {
  slotGrid.textContent = "";
  state.slots = slots;
  slotCount.textContent = `${slots.length} pol`;

  for (const slot of slots) {
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
    previewImage.draggable = false;
    previewImage.loading = "lazy";
    previewImage.decoding = "async";
    node.draggable = Boolean(selectedFile || loadedPhoto?.token || loadedPhoto?.ftp_token);
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
      renderSlots();
    });
    if (selectedFile || loadedPhoto) {
      const hasOpenableFile =
        Boolean(selectedFile) ||
        Boolean(selectedPhotoToken(loadedPhoto, slot.prefix)) ||
        Boolean(loadedPhoto?.ftp_filename) ||
        Boolean(sqlLinkFromPhoto(loadedPhoto));
      const hasFittablePreview =
        (selectedFile && isFileImageLike(selectedFile)) ||
        (loadedPhoto?.is_image && (selectedPhotoToken(loadedPhoto, slot.prefix) || loadedPhoto?.ftp_filename)) ||
        Boolean(sqlLinkFromPhoto(loadedPhoto));
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
        empty.textContent = selectedFile.name;
      }
    } else if (loadedPhoto) {
      preview.classList.add("loaded-photo");
      const thumb = thumbnailUrl(loadedPhoto, slot.prefix);
      if (thumb && (loadedPhoto.is_image || selectedSlotSource(slot.prefix, loadedPhoto) === "sql")) {
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
      if (!assignment || (assignment.type === "loaded" && !selectedPhotoToken(assignment.value, slot.prefix))) {
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
      const file = event.dataTransfer.files && event.dataTransfer.files[0] ? event.dataTransfer.files[0] : null;
      if (file) {
        state.draggedSlotPrefix = "";
        setSlotFile(slot.prefix, file);
        renderSlots();
      }
    });

    input.addEventListener("change", () => {
      const file = input.files && input.files[0] ? input.files[0] : null;
      if (!file) {
        state.files.delete(slot.prefix);
        renderSlots();
        return;
      }
      setSlotFile(slot.prefix, file);
      renderSlots();
    });

    slotGrid.appendChild(node);
  }
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
  submitButton.disabled = isBusy;
  formStatus.textContent = text;
}

function clearResult() {
  resultMeta.textContent = "";
  resultOutput.className = "result-output empty-state";
  resultOutput.textContent = "Brak wykonanych operacji.";
}

function showError(error) {
  resultMeta.textContent = "";
  resultOutput.className = "result-output error-text";
  resultOutput.textContent = error.message || String(error);
}

function showResult(payload) {
  resultOutput.className = "result-output";
  resultOutput.textContent = "";
  resultMeta.textContent = `${payload.saved_files.length} zapisanych`;
  const dir = document.createElement("p");
  dir.className = "ok-text";
  dir.textContent = payload.output_dir;
  resultOutput.appendChild(dir);
  if (payload.entry && payload.entry.product_id) {
    productForm.elements.product_id.value = payload.entry.product_id;
  }
  const list = document.createElement("ul");
  list.className = "result-list";
  for (const file of payload.saved_files || []) {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    const path = document.createElement("span");
    name.textContent = `${file.prefix} - ${file.filename}`;
    path.textContent = file.path;
    item.append(name, path);
    list.appendChild(item);
  }
  if ((payload.saved_files || []).length) {
    resultOutput.appendChild(list);
  } else {
    const noFiles = document.createElement("p");
    noFiles.className = "ok-text";
    noFiles.textContent = "Nie dodano nowych plikow; zapisano pozostale zmiany.";
    resultOutput.appendChild(noFiles);
  }
  if (payload.ftp?.enabled) {
    const ftp = document.createElement("p");
    ftp.className = payload.ftp.error ? "error-text" : "ok-text";
    ftp.textContent = payload.ftp.error
      ? `FTP: blad - ${payload.ftp.error}`
      : `FTP: wyslano ${payload.ftp.uploaded || 0}, usunieto ${payload.ftp.deleted || 0}, ${payload.ftp.elapsed_ms || 0} ms`;
    resultOutput.appendChild(ftp);
  }
  if (
    payload.local_delete?.deleted ||
    payload.local_delete?.skipped ||
    (payload.local_delete?.errors || []).length
  ) {
    const deletions = document.createElement("p");
    const deleteErrors = payload.local_delete?.errors || [];
    deletions.className = deleteErrors.length ? "error-text" : "ok-text";
    deletions.textContent = deleteErrors.length
      ? `Usuwanie lokalne: ${payload.local_delete.deleted || 0}, pominieto: ${
          payload.local_delete.skipped || 0
        }, bledy: ${deleteErrors.join("; ")}`
      : `Usunieto lokalnie: ${payload.local_delete.deleted || 0}, pominieto: ${
          payload.local_delete.skipped || 0
        }`;
    resultOutput.appendChild(deletions);
  }
  if (payload.sql?.enabled) {
    const sql = document.createElement("p");
    sql.className = payload.sql.error ? "error-text" : "ok-text";
    sql.textContent = payload.sql.error
      ? `SQL: blad - ${payload.sql.error}`
      : `SQL: aktualizacje ${payload.sql.updated || 0}, czyszczenia ${payload.sql.cleared || 0}`;
    resultOutput.appendChild(sql);
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

function renderHistoryDetails(group) {
  historyDetailTitle.textContent = `Historia EAN ${group.ean}`;
  historyDetailOutput.textContent = "";
  for (const item of group.items || []) {
    const row = document.createElement("article");
    const meta = document.createElement("div");
    const summary = document.createElement("strong");
    const details = document.createElement("span");
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
    row.append(meta, summary, details);
    historyDetailOutput.appendChild(row);
  }
  document.querySelector("#historyDetailModal").classList.add("active");
}

function renderHistory(payload) {
  state.history = payload;
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

async function loadHistory() {
  const params = new URLSearchParams({ user: historyUserFilter.value || "", limit: "300" });
  const payload = await requestJson(`/api/history?${params.toString()}`);
  renderHistory(payload);
}

function renderLogs(payload) {
  state.logs = payload;
  logsOutput.textContent = "";
  const logs = payload.logs || [];
  if (!logs.length) {
    logsOutput.className = "logs-output empty-state";
    logsOutput.textContent = "Brak dostepnych logow.";
    return;
  }
  logsOutput.className = "logs-output";
  for (const log of logs) {
    const block = document.createElement("article");
    const heading = document.createElement("div");
    const title = document.createElement("strong");
    const path = document.createElement("span");
    const lines = document.createElement("pre");
    block.className = "log-block";
    heading.className = "log-heading";
    title.textContent = log.label || log.key || "Log";
    path.textContent = log.path || "";
    lines.className = "log-lines";
    lines.textContent =
      (log.lines || []).join("\n") ||
      (log.exists ? "Plik logu jest pusty." : "Plik logu jeszcze nie istnieje.");
    heading.append(title, path);
    block.append(heading, lines);
    logsOutput.appendChild(block);
  }
}

async function loadLogs() {
  const payload = await requestJson("/api/logs?limit=400");
  renderLogs(payload);
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

function mergePhotoRecord(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming };
  for (const key of ["local", "ftp", "sql", "is_image"]) {
    merged[key] = Boolean(existing[key] || incoming[key]);
  }
  for (const key of [
    "filename",
    "path",
    "token",
    "url",
    "thumb_url",
    "ftp_filename",
    "ftp_path",
    "ftp_token",
    "ftp_url",
    "ftp_thumb_url",
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
  merged.prefix = incoming.prefix || existing.prefix || "";
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

function applyPhotoPayload(photos = []) {
  let changed = false;
  for (const photo of photos) {
    if (!photo?.prefix) continue;
    const existing = state.loadedPhotos.get(photo.prefix) || {};
    const merged = mergePhotoRecord(existing, photo);
    state.loadedPhotos.set(photo.prefix, merged);
    if (!state.slotSources.has(photo.prefix) || !selectedSlotSource(photo.prefix, merged)) {
      const source = defaultSlotSource(merged);
      if (source) state.slotSources.set(photo.prefix, source);
    }
    changed = true;
  }
  if (changed) {
    renderSlots();
  }
}

async function requestEntryPhotos(entry, source) {
  return requestJson(`/api/entries/photos?source=${encodeURIComponent(source)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
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
  const requestId = state.photoLoadRequestId + 1;
  state.photoLoadRequestId = requestId;
  state.photosLoading = true;
  state.loadedPhotos.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  const sources = progressive ? ["local", "sql", "ftp"] : ["all"];
  state.photoSourceStatus.clear();
  for (const source of sources) {
    state.photoSourceStatus.set(source, "pending");
  }
  formStatus.textContent = photoLoadingText();
  renderSlots();
  const tasks = sources.map(async (source) => {
    setPhotoSourceStatus(source, "loading", requestId);
    try {
      const payload = await requestEntryPhotos(entry, source);
      if (state.photoLoadRequestId === requestId) {
        setPhotoSourceStatus(source, "done", requestId);
        applyPhotoPayload(payload.photos || []);
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
    updateRuntimeMetrics();
    renderSlots();
  }
}

function fillForm(entry, options = {}) {
  state.suppressAutoSearch = true;
  state.loadedEntryOriginal = { ...entry };
  state.slotFits.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  productForm.elements.product_id.value = entry.product_id || "";
  productForm.elements.name.value = entry.name || "";
  productForm.elements.type_name.value = entry.type_name || "";
  productForm.elements.model.value = entry.model || "";
  productForm.elements.color1.value = entry.color1 || "";
  productForm.elements.color2.value = entry.color2 || "";
  productForm.elements.color3.value = entry.color3 || "";
  productForm.elements.extra.value = entry.extra || "";
  productForm.elements.ean.value = entry.ean || "";
  formStatus.textContent = entry.product_id ? `Wczytano ${entry.product_id}` : "Wczytano wpis";
  updateFieldWarnings();
  setTimeout(() => {
    state.suppressAutoSearch = false;
  }, 200);
  if (options.loadPhotos) {
    loadPhotosForEntry(entry).catch((error) => {
      formStatus.textContent = `Wpis wczytany, ale zdjecia nie: ${error.message}`;
    });
  }
}

async function refreshData() {
  const payload = await requestJson("/api/data");
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  state.fileIndex = payload.file_index || state.fileIndex;
  renderDatalists();
  renderEntrySelect();
  renderListEditor();
  updateRuntimeMetrics();
}

async function loadBootstrap() {
  const payload = await requestJson("/api/bootstrap");
  state.defaultSlotFit = Boolean(payload.auto_content_fit);
  if (versionInfo) {
    versionInfo.textContent = payload.version ? `Wersja ${payload.version}` : "";
  }
  serverInfo.textContent = payload.processed_dir;
  logoutButton.style.display = payload.auth_enabled ? "" : "none";
  state.currentUser = payload.current_user || null;
  updateAdminUi();
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  state.fileIndex = payload.file_index || null;
  renderDatalists();
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

async function saveEntryOnly() {
  const payload = await requestJson("/api/entries/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(formPayload()),
  });
  const entry = payload.entry || {};
  if (entry.product_id) {
    productForm.elements.product_id.value = entry.product_id;
  }
  state.loadedEntryOriginal = { ...formPayload(), product_id: productForm.elements.product_id.value };
  updateFieldWarnings();
  formStatus.textContent = entry.updated ? "Zaktualizowano wpis." : "Dodano nowy wpis.";
  await refreshData();
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
  const payload = await requestJson(`/api/lists/${state.selectedList}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
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
  if (attrs.checked !== undefined) input.checked = Boolean(attrs.checked);
  if (attrs.type === "checkbox") {
    input.value = "1";
  } else {
    input.value = value || "";
  }
  wrapper.appendChild(input);
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

function credentialField(name, label, isSet = false, attrs = {}) {
  const field = inputField(name, label, "", attrs);
  const input = field.querySelector("input");
  input.placeholder = isSet ? "Zapisane - wpisz nowe, zeby zmienic" : "Nie ustawiono";
  return field;
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
    settingsStatus.textContent = "Zapisywanie...";
    state.settings = await requestJson("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload(new FormData(form))),
    });
    state.currentUser = state.settings.current_user || state.currentUser;
    state.defaultSlotFit = Boolean(state.settings.auto_content_fit);
    updateAdminUi();
    if (Array.isArray(state.settings.slots)) {
      renderSlots(state.settings.slots);
    }
    settingsStatus.textContent = "Zapisano.";
    renderSettings();
  });
}

function renderSettingsApp() {
  const s = state.settings;
  const form = document.createElement("form");
  form.className = "settings-form";
  const configNote = document.createElement("p");
  configNote.className = "settings-note wide-field";
  configNote.textContent =
    "Panel webowy uzywa tej samej lokalizacji, config.json i APP_SECRET co lokalna aplikacja uruchomiona na backendzie.";
  const versionNote = document.createElement("p");
  versionNote.className = "settings-note wide-field";
  versionNote.textContent = `Wersja programu: ${s.version || "dev"}`;
  const colorGroup = document.createElement("div");
  colorGroup.className = "settings-field-group wide-field";
  const colorTitle = document.createElement("h2");
  colorTitle.textContent = "Nazwy pol kolorow";
  const colorGrid = document.createElement("div");
  colorGrid.className = "settings-form nested-grid";
  colorGrid.append(
    inputField("color1", "Kolor 1", s.color_field_labels?.color1 || ""),
    inputField("color2", "Kolor 2", s.color_field_labels?.color2 || ""),
    inputField("color3", "Kolor 3", s.color_field_labels?.color3 || "")
  );
  colorGroup.append(colorTitle, colorGrid);
  form.append(
    versionNote,
    configNote,
    inputField("base_dir", "Katalog bazowy", s.base_dir),
    checkField(
      "local_file_index",
      "Indeks plikow lokalnych",
      s.local_file_index,
      "Backend sprawdza lokalne pliki przy wczytywaniu statusow slotow."
    ),
    colorGroup,
    actionRow(diagnosticButton("local", "Test folderow backendu"), fileIndexRefreshButton())
  );
  settingsSaveButton(form, (data) => ({
    app: {
      base_dir: data.get("base_dir"),
      local_file_index: data.has("local_file_index"),
      color_field_labels: {
        color1: data.get("color1"),
        color2: data.get("color2"),
        color3: data.get("color3"),
      },
    },
  }));
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
    checkField(
      "auto_content_fit",
      "FIT domyslnie dla kazdego slotu",
      state.settings.auto_content_fit,
      "Nowe i wczytane sloty startuja z wlaczonym FIT, ale pojedynczy slot nadal mozna przelaczyc."
    ),
    checkField(
      "resize_enabled",
      "Zmniejszanie obrazu",
      p.resize_enabled,
      "Najdluzszy bok obrazu zostanie ograniczony do podanej liczby pikseli."
    ),
    inputField("max_dim", "Maksymalny bok (px)", p.max_dim || 2000, {
      type: "number",
      min: 64,
      max: 20000,
    }),
    checkField(
      "compress_enabled",
      "Kompresja JPG/WEBP",
      p.compress_enabled,
      "Uzywa podanej jakosci przy zapisie stratnych formatow."
    ),
    inputField("compress_quality", "Jakosc (%)", p.compress_quality || 85, {
      type: "number",
      min: 1,
      max: 100,
    }),
    checkField(
      "max_size_enabled",
      "Limit rozmiaru pliku",
      p.max_size_enabled,
      "Dla JPG/WEBP jakosc jest obnizana stopniowo, az plik miesci sie w limicie."
    ),
    inputField("max_file_kb", "Maksymalny rozmiar (KB)", p.max_file_kb || 500, {
      type: "number",
      min: 1,
      max: 102400,
    }),
    checkField(
      "convert_enabled",
      "Konwersja formatu obrazow",
      p.convert_enabled,
      "Obrazy sa zapisywane w wybranym formacie zamiast w formacie zrodlowym."
    ),
    selectField(
      "target_format",
      "Format docelowy",
      p.target_format || "PNG",
      formats.map((format) => [format, format])
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
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsFtp() {
  const ftp = state.settings.ftp;
  const form = document.createElement("form");
  form.className = "settings-form";
  form.append(
    checkField(
      "enabled",
      "Aktualizacja FTP",
      ftp.enabled,
      "Po zapisie backend bedzie wysylal przetworzone pliki na FTP."
    ),
    inputField("host", "Host", ftp.host),
    inputField("port", "Port", ftp.port, { type: "number" }),
    inputField("path", "Sciezka", ftp.path),
    credentialField("user", "Uzytkownik", ftp.user_set),
    credentialField("password", "Haslo", ftp.password_set, { type: "password" }),
    actionRow(diagnosticButton("ftp", "Test FTP"))
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

function renderSettingsSql() {
  const db = state.settings.database;
  const form = document.createElement("form");
  form.className = "settings-form";
  form.append(
    selectField("type", "Typ bazy", db.type, [["mysql", "MySQL"], ["mssql", "MS SQL"]]),
    checkField(
      "sql_update_enabled",
      "Aktualizacja SQL",
      db.sql_update_enabled,
      "Backend bedzie aktualizowal pola SQL przypisane w zakladce Sloty."
    ),
    inputField("query", "Zapytanie SQL", db.query, { textarea: true, className: "wide-field" }),
    inputField("mssql_server", "MS SQL server", db.mssql.server),
    inputField("mssql_database", "MS SQL database", db.mssql.database),
    credentialField("mssql_user", "MS SQL user", db.mssql.user_set),
    credentialField("mssql_password", "MS SQL haslo", db.mssql.password_set, { type: "password" }),
    inputField("mysql_server", "MySQL server", db.mysql.server),
    inputField("mysql_database", "MySQL database", db.mysql.database),
    credentialField("mysql_user", "MySQL user", db.mysql.user_set),
    credentialField("mysql_password", "MySQL haslo", db.mysql.password_set, { type: "password" }),
    actionRow(diagnosticButton("sql", "Test SQL"))
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
    },
  }));
  settingsOutput.appendChild(form);
}

function renderSettingsSlots() {
  ensureSqlColumnsDatalist();
  const form = document.createElement("form");
  form.className = "settings-form";
  const note = document.createElement("p");
  note.className = "settings-note wide-field";
  note.textContent = "Kazdy slot moze miec przypisane pole SQL uzywane przy sprawdzaniu i aktualizacji wpisu.";
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
    const column = inputField("sql_column", "Pole SQL", slot.sql_column || "");
    column.querySelector("input").setAttribute("list", "sqlColumnsList");
    remove.type = "button";
    remove.className = "secondary-button";
    remove.textContent = "Usun";
    remove.addEventListener("click", () => row.remove());
    row.append(
      inputField("prefix", "ID", slot.prefix),
      inputField("label", "Nazwa", slot.label),
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
    addSlotRow({ prefix: nextPrefix(), label: `Slot ${nextPrefix()}`, sql_column: "" });
  });
  form.append(note, list, actionRow(addButton));
  settingsSaveButton(form, () => {
    const slots = [...form.querySelectorAll(".slot-settings-row")].map((row) => ({
      prefix: row.querySelector('[name="prefix"]').value,
      label: row.querySelector('[name="label"]').value,
      sql_column: row.querySelector('[name="sql_column"]').value,
    }));
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
    const name = document.createElement("strong");
    const role = document.createElement("select");
    const enabled = document.createElement("input");
    const enabledWrap = document.createElement("div");
    const enabledText = document.createElement("div");
    const enabledTitle = document.createElement("strong");
    const enabledDescription = document.createElement("small");
    const passwordInput = document.createElement("input");
    const save = document.createElement("button");
    const isCurrentUser =
      state.currentUser &&
      String(state.currentUser.username || "").toLowerCase() === String(user.username || "").toLowerCase();
    name.textContent = user.username;
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
    row.append(name, role, passwordInput, enabledWrap, save);
    list.appendChild(row);
  }
  wrapper.append(addForm, list);
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
  if (state.activeSettingsTab === "ftp") renderSettingsFtp();
  if (state.activeSettingsTab === "sql") renderSettingsSql();
  if (state.activeSettingsTab === "slots") renderSettingsSlots();
  if (state.activeSettingsTab === "users") renderSettingsUsers();
}

async function loadSettings() {
  state.settings = await requestJson("/api/settings");
  state.currentUser = state.settings.current_user || state.currentUser;
  state.defaultSlotFit = Boolean(state.settings.auto_content_fit);
  updateAdminUi();
  renderSettings();
}

document.querySelectorAll("[data-modal]").forEach((button) => {
  button.addEventListener("click", () => openModal(button.dataset.modal));
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", closeModals);
});

document.querySelectorAll("[data-close-history-detail]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#historyDetailModal")?.classList.remove("active");
  });
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
  loadHistory().catch((error) => {
    historyOutput.textContent = error.message;
  });
});

historyRefreshButton?.addEventListener("click", () => {
  loadHistory().catch((error) => {
    historyOutput.textContent = error.message;
  });
});

logsRefreshButton?.addEventListener("click", () => {
  loadLogs().catch((error) => {
    logsOutput.textContent = error.message;
  });
});

entrySelect.addEventListener("change", () => {
  const option = entrySelect.selectedOptions[0];
  if (!option || !option.dataset.entry) return;
  fillForm(JSON.parse(option.dataset.entry), { loadPhotos: true });
});

for (const name of ["name", "type_name", "model"]) {
  productForm.elements[name].addEventListener("input", scheduleProductAutoSearch);
}

productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true, "Przetwarzanie...");
  clearResult();
  const data = new FormData(productForm);
  for (const [prefix, file] of state.files.entries()) {
    data.set(`slot_${prefix}`, file, file.name);
    data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
  }
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    const token = selectedPhotoToken(photo, prefix);
    if (!state.files.has(prefix) && photo.dirty && token) {
      data.set(`existing_slot_${prefix}`, token);
      data.set(`slot_fit_${prefix}`, isSlotFit(prefix) ? "1" : "0");
    }
  }
  for (const [prefix, item] of state.deletedSlots.entries()) {
    data.set(`delete_slot_${prefix}`, "1");
    if (item.token) data.set(`delete_local_slot_${prefix}`, item.token);
    if (item.ftp_filename) data.set(`delete_ftp_slot_${prefix}`, item.ftp_filename);
    if (item.sql) data.set(`delete_sql_slot_${prefix}`, "1");
  }
  try {
    const payload = await requestJson("/api/process", { method: "POST", body: data });
    showResult(payload);
    state.deletedSlots.clear();
    clearSelectedFiles();
    await refreshData();
    await loadPhotosForEntry({ ...formPayload(), product_id: payload.entry?.product_id || productForm.elements.product_id.value });
    setBusy(false, "Zakonczono.");
  } catch (error) {
    showError(error);
    setBusy(false, "");
  }
});

clearButton.addEventListener("click", () => {
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
  state.photoSourceStatus.clear();
  state.loadedEntryOriginal = null;
  state.lastAutoSearchKey = "";
  renderSlots();
  renderEntrySelect();
  updateFieldWarnings();
  clearResult();
  formStatus.textContent = "";
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

saveEntryButton.addEventListener("click", () => {
  saveEntryOnly().catch((error) => {
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
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
  window.location.href = "/";
});

setupAutocomplete();
setupFieldChangeTracking();
applyTheme();
loadBootstrap().catch(showError);
setInterval(() => {
  refreshFileIndexStatus().catch(() => {});
}, 5000);
