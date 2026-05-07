const state = {
  slots: [],
  files: new Map(),
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

function fileLabel(file) {
  if (!file) {
    return "Brak pliku";
  }
  const kb = Math.max(1, Math.round(file.size / 1024));
  return `${file.name} (${kb} KB)`;
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

async function loadBootstrap() {
  const payload = await requestJson("/api/bootstrap");
  serverInfo.textContent = payload.processed_dir;
  renderSlots(payload.slots);
}

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
    setBusy(false, "Zakonczono.");
  } catch (error) {
    showError(error);
    setBusy(false, "");
  }
});

clearButton.addEventListener("click", () => {
  productForm.reset();
  state.files.clear();
  renderSlots(state.slots);
  clearResult();
  formStatus.textContent = "";
});

logoutButton.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
  window.location.href = "/login";
});

loadBootstrap().catch(showError);
