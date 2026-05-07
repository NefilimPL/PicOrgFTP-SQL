const state = {
  slots: [],
  files: new Map(),
  lists: {},
  entries: [],
  selectedList: "names",
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

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Sesja wygasla.");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Operacja nie powiodla sie.");
  }
  return payload;
}

function setView(viewName) {
  document.querySelectorAll(".app-view").forEach((view) => {
    view.classList.toggle("active", view.id === `${viewName}View`);
  });
  document.querySelectorAll(".nav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  if (viewName === "settings") {
    loadSettings().catch((error) => {
      settingsStatus.textContent = error.message;
    });
  }
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

function renderSlots(slots) {
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

    title.textContent = `${slot.prefix} - ${slot.label}`;
    detail.textContent = "Brak pliku";
    input.name = `slot_${slot.prefix}`;

    input.addEventListener("change", () => {
      const file = input.files && input.files[0] ? input.files[0] : null;
      if (!file) {
        state.files.delete(slot.prefix);
        preview.classList.remove("has-image");
        previewImage.removeAttribute("src");
        empty.textContent = "Brak pliku";
        detail.textContent = "Brak pliku";
        return;
      }

      state.files.set(slot.prefix, file);
      detail.textContent = fileLabel(file);
      if (file.type.startsWith("image/")) {
        previewImage.src = URL.createObjectURL(file);
        preview.classList.add("has-image");
      } else {
        preview.classList.remove("has-image");
        previewImage.removeAttribute("src");
        empty.textContent = file.name;
      }
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
    text.textContent = value;
    const remove = document.createElement("button");
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

function fillForm(entry) {
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
    fillForm(payload.entries[0]);
  } else {
    formStatus.textContent = `${(payload.entries || []).length} dopasowan po EAN.`;
  }
}

async function searchByProduct() {
  const fields = formPayload();
  const params = new URLSearchParams({
    name: fields.name,
    type_name: fields.type_name,
    model: fields.model,
  });
  const payload = await requestJson(`/api/entries/search?${params.toString()}`);
  renderEntrySelect(payload.entries || []);
  formStatus.textContent = `${(payload.entries || []).length} dopasowan produktu.`;
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

function settingsRow(label, value) {
  const row = document.createElement("div");
  row.className = "settings-row";
  const key = document.createElement("span");
  const val = document.createElement("span");
  key.textContent = label;
  val.textContent = value === true ? "Tak" : value === false ? "Nie" : String(value ?? "");
  row.append(key, val);
  return row;
}

function settingsBlock(title, rows) {
  const block = document.createElement("article");
  block.className = "settings-block";
  const heading = document.createElement("h2");
  heading.textContent = title;
  block.appendChild(heading);
  for (const row of rows) {
    block.appendChild(settingsRow(row[0], row[1]));
  }
  return block;
}

async function loadSettings() {
  const payload = await requestJson("/api/settings");
  settingsOutput.textContent = "";
  settingsStatus.textContent = payload.windows_admin
    ? "Backend dziala jako administrator Windows."
    : "Backend nie jest uruchomiony jako administrator Windows.";
  settingsOutput.append(
    settingsBlock("Aplikacja", [
      ["Katalog bazowy", payload.base_dir],
      ["Katalog zdjec", payload.processed_dir],
      ["Config", payload.config_path],
      ["Indeks plikow", payload.local_file_index],
      ["Auto fit", payload.auto_content_fit],
    ]),
    settingsBlock("FTP", [
      ["Wlaczone", payload.ftp.enabled],
      ["Host", payload.ftp.host],
      ["Port", payload.ftp.port],
      ["Sciezka", payload.ftp.path],
      ["User", payload.ftp.user_set ? "ustawiony" : "brak"],
      ["Haslo", payload.ftp.password_set ? "ustawione" : "brak"],
    ]),
    settingsBlock("SQL", [
      ["Typ", payload.database.type],
      ["Update SQL", payload.database.sql_update_enabled],
      ["MSSQL", `${payload.database.mssql.server} / ${payload.database.mssql.database}`],
      ["MySQL", `${payload.database.mysql.server} / ${payload.database.mysql.database}`],
      ["Mapowania", payload.sql_map_count],
      ["Kolumny", payload.sql_available_columns_count],
    ])
  );
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

entrySelect.addEventListener("change", () => {
  const option = entrySelect.selectedOptions[0];
  if (!option || !option.dataset.entry) {
    return;
  }
  fillForm(JSON.parse(option.dataset.entry));
});

productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true, "Przetwarzanie...");
  clearResult();

  const data = new FormData(productForm);
  for (const [prefix, file] of state.files.entries()) {
    data.set(`slot_${prefix}`, file, file.name);
  }

  try {
    const payload = await requestJson("/api/process", {
      method: "POST",
      body: data,
    });
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
  renderSlots(state.slots);
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
  window.location.href = "/login";
});

loadBootstrap().catch(showError);
