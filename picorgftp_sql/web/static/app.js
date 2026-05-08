const state = {
  slots: [],
  files: new Map(),
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
  slotSources: new Map(),
  draggedSlotPrefix: "",
  lastLookupMs: null,
  activeSettingsTab: "app",
  history: null,
  theme: localStorage.getItem("picorg-theme") || "light",
  suppressAutoSearch: false,
  lastAutoSearchKey: "",
};

const listLabels = {
  names: "Nazwy",
  types: "Typy",
  models: "Modele",
  colors: "Kolory",
  extras: "Dodatki",
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
const submitButton = document.querySelector("#submitButton");
const clearButton = document.querySelector("#clearButton");
const logoutButton = document.querySelector("#logoutButton");
const themeToggleButton = document.querySelector("#themeToggleButton");
const settingsNavButton = document.querySelector('[data-modal="settings"]');
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

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
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
  if (settingsNavButton) {
    settingsNavButton.style.display = state.isAdmin ? "" : "none";
  }
}

function applyTheme() {
  document.body.dataset.theme = state.theme;
  if (themeToggleButton) {
    themeToggleButton.textContent = state.theme === "dark" ? "Jasny" : "Ciemny";
  }
  localStorage.setItem("picorg-theme", state.theme);
}

function openModal(name) {
  if (name === "settings" && !state.isAdmin) {
    formStatus.textContent = "Ustawienia sa dostepne tylko dla administratora.";
    return;
  }
  document.querySelector(`#${name}View`)?.classList.add("active");
  document.querySelector(`#${name}Modal`)?.classList.add("active");
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
}

function closeModals() {
  document.querySelectorAll(".modal-view").forEach((modal) => modal.classList.remove("active"));
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

function closeAutocompletePanels(exceptPanel = null) {
  document.querySelectorAll(".autocomplete-panel").forEach((panel) => {
    if (panel !== exceptPanel) panel.classList.remove("active");
  });
}

function renderAutocompletePanel(input, panel, values) {
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
}

function setupAutocomplete() {
  productForm.setAttribute("autocomplete", "off");
  for (const fieldName of Object.keys(fieldListKey)) {
    const input = productForm.elements[fieldName];
    if (!input) continue;
    input.removeAttribute("list");
    input.setAttribute("autocomplete", "new-password");
    input.setAttribute("spellcheck", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("data-lpignore", "true");
    const host = input.closest("label");
    if (!host) continue;
    host.classList.add("autocomplete-host");
    const panel = document.createElement("div");
    panel.className = "autocomplete-panel";
    host.appendChild(panel);
    let requestId = 0;
    let remoteTimer = 0;
    const refresh = () => {
      closeAutocompletePanels(panel);
      const local = localSuggestions(fieldName);
      renderAutocompletePanel(input, panel, local);
      const currentRequest = ++requestId;
      window.clearTimeout(remoteTimer);
      remoteTimer = window.setTimeout(() => {
        remoteSuggestions(fieldName)
          .then((values) => {
            if (currentRequest === requestId) {
              renderAutocompletePanel(input, panel, uniqueValues([...values, ...local]));
            }
          })
          .catch(() => {});
      }, 180);
    };
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
    const canPreview = (key === "local" && photo?.token) || (key === "ftp" && photo?.ftp_filename);
    const badge = document.createElement(canPreview ? "button" : "span");
    badge.dataset.source = key;
    badge.className = `slot-badge slot-badge-${key} ${photo && photo[key] ? "on" : ""} ${
      selectedSlotSource(prefix, photo) === key ? "selected" : ""
    }`;
    badge.title = title;
    badge.textContent = label;
    if (canPreview) {
      badge.type = "button";
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
  container.appendChild(badges);
}

async function loadFtpPreview(photo, prefix) {
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
  state.loadedPhotos.set(prefix, updated);
  state.slotSources.set(prefix, "ftp");
  updateSlotPreview(prefix);
}

function isSlotFit(prefix) {
  return Boolean(state.slotFits.get(prefix));
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
  const markDelete = options.markDelete !== false;
  if (markDelete) {
    markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
  }
  state.files.delete(prefix);
  state.loadedPhotos.delete(prefix);
  state.slotFits.delete(prefix);
  state.slotSources.delete(prefix);
}

function setSlotFile(prefix, file) {
  markSlotDeletion(prefix, state.loadedPhotos.get(prefix));
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
  detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto, prefix);
  card.querySelectorAll(".slot-badge[data-source]").forEach((badge) => {
    badge.classList.toggle("selected", selectedSlotSource(prefix, loadedPhoto) === badge.dataset.source);
  });
  if (fitButton) {
    fitButton.classList.toggle("active", isSlotFit(prefix));
  }
  if (selectedFile) return;
  preview.classList.remove("has-image", "thumb-loading", "loaded-photo");
  previewImage.removeAttribute("src");
  empty.textContent = "Brak pliku";
  if (!loadedPhoto) return;
  preview.classList.add("loaded-photo");
  const thumb = thumbnailUrl(loadedPhoto, prefix);
  if (loadedPhoto.is_image && thumb) {
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
    const clearButton = document.createElement("button");
    node.dataset.slotPrefix = slot.prefix;

    title.textContent = `${slot.prefix} - ${slot.label}`;
    detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto, slot.prefix);
    input.name = `slot_${slot.prefix}`;
    previewImage.draggable = false;
    previewImage.loading = "lazy";
    previewImage.decoding = "async";
    node.draggable = Boolean(selectedFile || loadedPhoto?.token || loadedPhoto?.ftp_token);
    renderSlotBadges(meta, loadedPhoto, selectedFile, slot.prefix);
    overlay.className = "slot-loading-overlay";
    overlay.innerHTML = '<span>Wczytywanie</span><div class="progress-line"><i></i></div>';
    if (state.photosLoading) {
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
    clearButton.type = "button";
    clearButton.className = "slot-clear-button";
    clearButton.textContent = "Usun";
    clearButton.title = "Usun plik z tego slotu w formularzu";
    clearButton.addEventListener("click", (event) => {
      event.stopPropagation();
      clearSlotAssignment(slot.prefix);
      formStatus.textContent = `Wyczyszczono slot ${slot.prefix}.`;
      renderSlots();
    });
    if (selectedFile || loadedPhoto) {
      if (selectedFile || loadedPhoto?.token || loadedPhoto?.ftp_token) {
        controls.appendChild(fitButton);
      }
      controls.appendChild(clearButton);
      meta.appendChild(controls);
    }

    if (selectedFile) {
      if (selectedFile.type.startsWith("image/")) {
        previewImage.src = URL.createObjectURL(selectedFile);
        preview.classList.add("has-image");
      } else {
        empty.textContent = selectedFile.name;
      }
    } else if (loadedPhoto) {
      preview.classList.add("loaded-photo");
      const thumb = thumbnailUrl(loadedPhoto, slot.prefix);
      if (loadedPhoto.is_image && thumb) {
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
      renderListEditor();
    });
    listTabs.appendChild(button);
  }
}

function renderListEditor() {
  renderListTabs();
  listValues.textContent = "";
  listAddInput.value = "";
  listAddInput.placeholder = `Nowa wartosc: ${listLabels[state.selectedList]}`;
  for (const value of state.lists[state.selectedList] || []) {
    const row = document.createElement("div");
    row.className = "list-value-row";
    const text = document.createElement("span");
    const remove = document.createElement("button");
    text.textContent = value;
    remove.type = "button";
    remove.className = "icon-button";
    remove.textContent = "X";
    remove.title = "Usun";
    remove.addEventListener("click", () => removeListValue(value));
    row.append(text, remove);
    listValues.appendChild(row);
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
  for (const file of payload.saved_files) {
    const item = document.createElement("li");
    const name = document.createElement("strong");
    const path = document.createElement("span");
    name.textContent = `${file.prefix} - ${file.filename}`;
    path.textContent = file.path;
    item.append(name, path);
    list.appendChild(item);
  }
  resultOutput.appendChild(list);
  if (payload.ftp?.enabled) {
    const ftp = document.createElement("p");
    ftp.className = payload.ftp.error ? "error-text" : "ok-text";
    ftp.textContent = payload.ftp.error
      ? `FTP: blad - ${payload.ftp.error}`
      : `FTP: wyslano ${payload.ftp.uploaded || 0}, usunieto ${payload.ftp.deleted || 0}, ${payload.ftp.elapsed_ms || 0} ms`;
    resultOutput.appendChild(ftp);
  }
  if (payload.local_delete?.deleted || payload.local_delete?.skipped) {
    const deletions = document.createElement("p");
    deletions.className = "ok-text";
    deletions.textContent = `Usunieto lokalnie: ${payload.local_delete.deleted || 0}`;
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

function historyEntryLabel(entry) {
  return [entry.NAZWA || entry.name, entry.TYP || entry.type_name, entry.MODEL || entry.model]
    .filter(Boolean)
    .join(" / ");
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
      saved ? `zapisane pliki: ${saved}` : "",
      deleted ? `usuniete sloty: ${deleted}` : "",
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
    fields.textContent = historyEntryLabel(entry) || "Brak danych pól tekstowych";
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

async function loadPhotosForEntry(entry) {
  const started = performance.now();
  state.photosLoading = true;
  state.loadedPhotos.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
  renderSlots();
  try {
    const payload = await requestJson("/api/entries/photos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(entry),
    });
    state.loadedPhotos.clear();
    state.deletedSlots.clear();
    state.slotSources.clear();
    for (const photo of payload.photos || []) {
      state.loadedPhotos.set(photo.prefix, photo);
      const source = defaultSlotSource(photo);
      if (source) state.slotSources.set(photo.prefix, source);
    }
    state.lastLookupMs = performance.now() - started;
  } finally {
    state.photosLoading = false;
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
  const payload = await requestJson(`/api/lists/${state.selectedList}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  state.lists = payload.lists || {};
  state.entries = payload.entries || state.entries;
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
    configNote,
    inputField("base_dir", "Katalog bazowy", s.base_dir),
    checkField(
      "local_file_index",
      "Indeks plikow lokalnych",
      s.local_file_index,
      "Backend sprawdza lokalne pliki przy wczytywaniu statusow slotow."
    ),
    checkField(
      "auto_content_fit",
      "Automatyczne dopasowanie zdjec",
      s.auto_content_fit,
      "Przed zapisem zdjecia sa przycinane do widocznej zawartosci."
    ),
    colorGroup,
    actionRow(diagnosticButton("local", "Test folderow backendu"), fileIndexRefreshButton())
  );
  settingsSaveButton(form, (data) => ({
    app: {
      base_dir: data.get("base_dir"),
      local_file_index: data.has("local_file_index"),
      auto_content_fit: data.has("auto_content_fit"),
      color_field_labels: {
        color1: data.get("color1"),
        color2: data.get("color2"),
        color3: data.get("color3"),
      },
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
  if (state.activeSettingsTab === "ftp") renderSettingsFtp();
  if (state.activeSettingsTab === "sql") renderSettingsSql();
  if (state.activeSettingsTab === "slots") renderSettingsSlots();
  if (state.activeSettingsTab === "users") renderSettingsUsers();
}

async function loadSettings() {
  state.settings = await requestJson("/api/settings");
  state.currentUser = state.settings.current_user || state.currentUser;
  updateAdminUi();
  renderSettings();
}

document.querySelectorAll(".nav-button").forEach((button) => {
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
    if (isSlotFit(prefix)) {
      data.set(`slot_fit_${prefix}`, "1");
    }
  }
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    const token = selectedPhotoToken(photo, prefix);
    if (!state.files.has(prefix) && photo.dirty && token) {
      data.set(`existing_slot_${prefix}`, token);
      if (isSlotFit(prefix)) {
        data.set(`slot_fit_${prefix}`, "1");
      }
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
    await refreshData();
    setBusy(false, "Zakonczono.");
  } catch (error) {
    showError(error);
    setBusy(false, "");
  }
});

clearButton.addEventListener("click", () => {
  productForm.reset();
  productForm.elements.product_id.value = "";
  state.files.clear();
  state.loadedPhotos.clear();
  state.slotFits.clear();
  state.deletedSlots.clear();
  state.slotSources.clear();
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
