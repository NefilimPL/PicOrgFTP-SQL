const state = {
  slots: [],
  files: new Map(),
  loadedPhotos: new Map(),
  lists: {},
  entries: [],
  selectedList: "names",
  settings: null,
  currentUser: null,
  isAdmin: false,
  activeSettingsTab: "app",
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
const serverInfo = document.querySelector("#serverInfo");
const submitButton = document.querySelector("#submitButton");
const clearButton = document.querySelector("#clearButton");
const logoutButton = document.querySelector("#logoutButton");
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

function slotStatusText(photo) {
  if (!photo) {
    return "Przeciagnij albo wybierz plik";
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

function renderSlotBadges(container, photo, file) {
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
    const badge = document.createElement("span");
    badge.className = `slot-badge ${photo && photo[key] ? "on" : ""}`;
    badge.title = title;
    badge.textContent = label;
    badges.appendChild(badge);
  }
  container.appendChild(badges);
}

function clearSlotAssignment(prefix) {
  state.files.delete(prefix);
  state.loadedPhotos.delete(prefix);
}

function setSlotFile(prefix, file) {
  state.files.set(prefix, file);
  state.loadedPhotos.delete(prefix);
}

function getSlotAssignment(prefix) {
  if (state.files.has(prefix)) {
    return { type: "file", value: state.files.get(prefix) };
  }
  if (state.loadedPhotos.has(prefix)) {
    return { type: "loaded", value: state.loadedPhotos.get(prefix) };
  }
  return null;
}

function setSlotAssignment(prefix, assignment) {
  clearSlotAssignment(prefix);
  if (!assignment) {
    return;
  }
  if (assignment.type === "file") {
    state.files.set(prefix, assignment.value);
    return;
  }
  if (assignment.type === "loaded") {
    state.loadedPhotos.set(prefix, { ...assignment.value, prefix, dirty: true });
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
  setSlotAssignment(targetPrefix, source);
  setSlotAssignment(sourcePrefix, target);
  renderSlots();
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
    const loadedPhoto = state.loadedPhotos.get(slot.prefix);
    const selectedFile = state.files.get(slot.prefix);

    title.textContent = `${slot.prefix} - ${slot.label}`;
    detail.textContent = selectedFile ? fileLabel(selectedFile) : slotStatusText(loadedPhoto);
    input.name = `slot_${slot.prefix}`;
    node.draggable = Boolean(selectedFile || loadedPhoto?.token);
    renderSlotBadges(node.querySelector(".slot-meta"), loadedPhoto, selectedFile);

    if (selectedFile) {
      if (selectedFile.type.startsWith("image/")) {
        previewImage.src = URL.createObjectURL(selectedFile);
        preview.classList.add("has-image");
      } else {
        empty.textContent = selectedFile.name;
      }
    } else if (loadedPhoto) {
      preview.classList.add("loaded-photo");
      if (loadedPhoto.is_image && loadedPhoto.url) {
        previewImage.src = loadedPhoto.url;
        preview.classList.add("has-image");
      } else {
        empty.textContent = slotStatusText(loadedPhoto);
      }
    }

    node.addEventListener("dragstart", (event) => {
      const assignment = getSlotAssignment(slot.prefix);
      if (!assignment || (assignment.type === "loaded" && !assignment.value.token)) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.setData("text/plain", slot.prefix);
      event.dataTransfer.effectAllowed = "move";
    });
    node.addEventListener("dragover", (event) => {
      event.preventDefault();
      node.classList.add("drag-over");
      event.dataTransfer.dropEffect = event.dataTransfer.files?.length ? "copy" : "move";
    });
    node.addEventListener("dragleave", () => {
      node.classList.remove("drag-over");
    });
    node.addEventListener("drop", (event) => {
      event.preventDefault();
      node.classList.remove("drag-over");
      const file = event.dataTransfer.files && event.dataTransfer.files[0] ? event.dataTransfer.files[0] : null;
      if (file) {
        setSlotFile(slot.prefix, file);
        renderSlots();
        return;
      }
      moveSlotContent(event.dataTransfer.getData("text/plain"), slot.prefix);
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
  const payload = await requestJson("/api/entries/photos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  state.loadedPhotos.clear();
  for (const photo of payload.photos || []) {
    state.loadedPhotos.set(photo.prefix, photo);
  }
  renderSlots();
}

function fillForm(entry, options = {}) {
  state.suppressAutoSearch = true;
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
  renderDatalists();
  renderEntrySelect();
  renderListEditor();
}

async function loadBootstrap() {
  const payload = await requestJson("/api/bootstrap");
  serverInfo.textContent = payload.processed_dir;
  logoutButton.style.display = payload.auth_enabled ? "" : "none";
  state.currentUser = payload.current_user || null;
  updateAdminUi();
  state.lists = payload.lists || {};
  state.entries = payload.entries || [];
  renderDatalists();
  renderEntrySelect();
  renderSlots(payload.slots || []);
  renderListEditor();
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
    actionRow(diagnosticButton("local", "Test folderow backendu"))
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
  list.className = "slot-settings-list";
  for (const slot of state.settings.slots || []) {
    const row = document.createElement("div");
    row.className = "slot-settings-row";
    const column = inputField("sql_column", "Pole SQL", slot.sql_column || "");
    column.querySelector("input").setAttribute("list", "sqlColumnsList");
    row.append(
      inputField("prefix", "ID", slot.prefix),
      inputField("label", "Nazwa", slot.label),
      column
    );
    list.appendChild(row);
  }
  form.append(note, list);
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

document.querySelectorAll(".settings-tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.activeSettingsTab = button.dataset.settingsTab;
    renderSettings();
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
  }
  for (const [prefix, photo] of state.loadedPhotos.entries()) {
    if (!state.files.has(prefix) && photo.dirty && photo.token) {
      data.set(`existing_slot_${prefix}`, photo.token);
    }
  }
  try {
    const payload = await requestJson("/api/process", { method: "POST", body: data });
    showResult(payload);
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
  state.lastAutoSearchKey = "";
  renderSlots();
  renderEntrySelect();
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

loadBootstrap().catch(showError);
