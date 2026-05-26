const QUEUE_KEY = "uploadQueue";
const STATUS_KEY = "uploadStatus";
const ALARM_NAME = "picorg-upload-queue";

let processing = false;

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve));
}

function storageSet(values) {
  return new Promise((resolve) => chrome.storage.local.set(values, resolve));
}

function normalizePanelUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function imageFilename(url, fallback = "web-image.jpg") {
  try {
    const path = new URL(url).pathname;
    const name = decodeURIComponent(path.split("/").pop() || "").trim();
    return name || fallback;
  } catch (_error) {
    return fallback;
  }
}

function imageMimeType(url, fallback = "image/jpeg") {
  const lower = String(url || "").toLowerCase().split("?", 1)[0];
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".bmp")) return "image/bmp";
  if (lower.endsWith(".avif")) return "image/avif";
  return fallback;
}

async function setBadge(status) {
  const remaining = Number(status?.remaining || 0);
  if (remaining > 0) {
    await chrome.action.setBadgeBackgroundColor({ color: "#2f6f5e" });
    await chrome.action.setBadgeText({ text: String(Math.min(remaining, 99)) });
  } else if (Number(status?.failed || 0) > 0) {
    await chrome.action.setBadgeBackgroundColor({ color: "#b42318" });
    await chrome.action.setBadgeText({ text: "!" });
  } else {
    await chrome.action.setBadgeText({ text: "" });
  }
}

async function updateStatus(patch) {
  const stored = await storageGet([STATUS_KEY, QUEUE_KEY]);
  const queue = stored[QUEUE_KEY] || [];
  const status = {
    running: false,
    total: 0,
    uploaded: 0,
    failed: 0,
    remaining: queue.length,
    lastError: "",
    ...(stored[STATUS_KEY] || {}),
    ...patch,
    updatedAt: Date.now(),
  };
  await storageSet({ [STATUS_KEY]: status });
  await setBadge(status);
  return status;
}

async function uploadOne(item, settings) {
  const image = item.image || item;
  const imageUrl = String(image.url || "");
  const pageUrl = String(item.pageUrl || image.pageUrl || "");
  const panelUrl = normalizePanelUrl(settings.panelUrl);
  const apiToken = String(settings.apiToken || "").trim();
  if (!panelUrl || !apiToken) {
    throw new Error("Brak adresu panelu albo tokenu.");
  }
  const imageResponse = await fetch(imageUrl, {
    credentials: "include",
    cache: "no-cache",
  });
  if (!imageResponse.ok) {
    throw new Error(`Nie udalo sie pobrac obrazu ${imageResponse.status}: ${imageUrl}`);
  }
  const blob = await imageResponse.blob();
  const filename = imageFilename(imageUrl);
  const form = new FormData();
  form.append("file", blob, filename);
  form.append("prefix", "web");
  form.append("source_url", imageUrl);
  form.append("page_url", pageUrl);

  const uploadResponse = await fetch(`${panelUrl}/api/browser-extension/upload-cache`, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiToken}` },
    body: form,
  });
  const payload = await uploadResponse.json().catch(() => ({}));
  if (!uploadResponse.ok) {
    throw new Error(payload.detail || `Panel odrzucil upload: ${uploadResponse.status}`);
  }
  return {
    ...payload,
    mime_type: blob.type || imageMimeType(imageUrl),
  };
}

async function processQueue() {
  if (processing) return;
  processing = true;
  try {
    while (true) {
      const stored = await storageGet([QUEUE_KEY, STATUS_KEY, "panelUrl", "apiToken"]);
      const queue = stored[QUEUE_KEY] || [];
      const status = stored[STATUS_KEY] || {};
      if (!queue.length) {
        await updateStatus({ running: false, remaining: 0 });
        await chrome.alarms.clear(ALARM_NAME);
        return;
      }
      await updateStatus({ running: true, remaining: queue.length });
      const item = queue[0];
      try {
        await uploadOne(item, {
          panelUrl: stored.panelUrl,
          apiToken: stored.apiToken,
        });
        const nextQueue = queue.slice(1);
        await storageSet({ [QUEUE_KEY]: nextQueue });
        await updateStatus({
          running: true,
          uploaded: Number(status.uploaded || 0) + 1,
          remaining: nextQueue.length,
          lastError: "",
        });
      } catch (error) {
        const nextQueue = queue.slice(1);
        await storageSet({ [QUEUE_KEY]: nextQueue });
        await updateStatus({
          running: true,
          failed: Number(status.failed || 0) + 1,
          remaining: nextQueue.length,
          lastError: error.message || String(error),
        });
      }
    }
  } finally {
    processing = false;
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "startUpload") {
    (async () => {
      const images = Array.isArray(message.images) ? message.images : [];
      const queue = images.map((image) => ({
        image,
        pageUrl: message.pageUrl || "",
      }));
      await storageSet({
        [QUEUE_KEY]: queue,
        [STATUS_KEY]: {
          running: true,
          total: queue.length,
          uploaded: 0,
          failed: 0,
          remaining: queue.length,
          lastError: "",
          updatedAt: Date.now(),
        },
      });
      await chrome.alarms.create(ALARM_NAME, { periodInMinutes: 1 });
      processQueue();
      sendResponse({ ok: true, total: queue.length });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "getUploadStatus") {
    storageGet([STATUS_KEY, QUEUE_KEY])
      .then((stored) => {
        const status = stored[STATUS_KEY] || {};
        sendResponse({
          ok: true,
          status: {
            running: Boolean(status.running),
            total: Number(status.total || 0),
            uploaded: Number(status.uploaded || 0),
            failed: Number(status.failed || 0),
            remaining: (stored[QUEUE_KEY] || []).length,
            lastError: status.lastError || "",
          },
        });
      })
      .catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  return false;
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    processQueue();
  }
});

chrome.runtime.onStartup.addListener(() => {
  processQueue();
});
