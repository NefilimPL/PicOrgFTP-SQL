const QUEUE_KEY = "uploadQueue";
const FAILED_KEY = "uploadFailed";
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

function queueItemUrl(item) {
  const image = item?.image || item || {};
  return String(image.url || "");
}

function queueItemsMatch(left, right) {
  return (
    queueItemUrl(left) === queueItemUrl(right) &&
    String(left?.pageUrl || "") === String(right?.pageUrl || "")
  );
}

function queueWithoutItem(queue, item) {
  const index = queue.findIndex((candidate) => queueItemsMatch(candidate, item));
  const removeIndex = index >= 0 ? index : queue.length ? 0 : -1;
  if (removeIndex < 0) return [];
  return [...queue.slice(0, removeIndex), ...queue.slice(removeIndex + 1)];
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
  const stored = await storageGet([STATUS_KEY, QUEUE_KEY, FAILED_KEY]);
  const queue = stored[QUEUE_KEY] || [];
  const failedQueue = stored[FAILED_KEY] || [];
  const status = {
    running: false,
    total: 0,
    uploaded: 0,
    failed: 0,
    remaining: queue.length,
    failedRetryable: failedQueue.length,
    lastError: "",
    ...(stored[STATUS_KEY] || {}),
    ...patch,
    failedRetryable: failedQueue.length,
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
      const stored = await storageGet([QUEUE_KEY, FAILED_KEY, STATUS_KEY, "panelUrl", "apiToken"]);
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
        const latest = await storageGet([QUEUE_KEY]);
        const nextQueue = queueWithoutItem(latest[QUEUE_KEY] || [], item);
        await storageSet({ [QUEUE_KEY]: nextQueue });
        await updateStatus({
          running: true,
          uploaded: Number(status.uploaded || 0) + 1,
          remaining: nextQueue.length,
          lastError: "",
        });
      } catch (error) {
        const latest = await storageGet([QUEUE_KEY, FAILED_KEY]);
        const nextQueue = queueWithoutItem(latest[QUEUE_KEY] || [], item);
        const message = error.message || String(error);
        await storageSet({
          [QUEUE_KEY]: nextQueue,
          [FAILED_KEY]: [
            ...(latest[FAILED_KEY] || []),
            {
              ...item,
              error: message,
              failedAt: Date.now(),
            },
          ],
        });
        await updateStatus({
          running: true,
          failed: Number(status.failed || 0) + 1,
          remaining: nextQueue.length,
          lastError: message,
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
      const incomingQueue = images.map((image) => ({
        image,
        pageUrl: message.pageUrl || "",
      }));
      const stored = await storageGet([QUEUE_KEY, FAILED_KEY, STATUS_KEY]);
      const queue = stored[QUEUE_KEY] || [];
      const status = stored[STATUS_KEY] || {};
      const hasActiveUpload = Boolean(status.running) || queue.length > 0;
      const nextQueue = hasActiveUpload ? [...queue, ...incomingQueue] : incomingQueue;
      const uploaded = hasActiveUpload ? Number(status.uploaded || 0) : 0;
      const failed = hasActiveUpload ? Number(status.failed || 0) : 0;
      const total = hasActiveUpload
        ? Number(status.total || uploaded + failed + queue.length) + incomingQueue.length
        : incomingQueue.length;
      await storageSet({
        [QUEUE_KEY]: nextQueue,
        [FAILED_KEY]: hasActiveUpload ? stored[FAILED_KEY] || [] : [],
        [STATUS_KEY]: {
          running: true,
          total,
          uploaded,
          failed,
          remaining: nextQueue.length,
          failedRetryable: hasActiveUpload ? (stored[FAILED_KEY] || []).length : 0,
          lastError: "",
          updatedAt: Date.now(),
        },
      });
      await chrome.alarms.create(ALARM_NAME, { periodInMinutes: 1 });
      processQueue();
      sendResponse({ ok: true, total: incomingQueue.length, queued: nextQueue.length });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "retryFailed") {
    (async () => {
      const stored = await storageGet([QUEUE_KEY, FAILED_KEY, STATUS_KEY]);
      const failedQueue = stored[FAILED_KEY] || [];
      if (!failedQueue.length) {
        sendResponse({ ok: true, total: 0, queued: (stored[QUEUE_KEY] || []).length });
        return;
      }
      const queue = stored[QUEUE_KEY] || [];
      const nextQueue = [...queue, ...failedQueue.map(({ error, failedAt, ...item }) => item)];
      const status = stored[STATUS_KEY] || {};
      const uploaded = Number(status.uploaded || 0);
      await storageSet({
        [QUEUE_KEY]: nextQueue,
        [FAILED_KEY]: [],
        [STATUS_KEY]: {
          ...status,
          running: true,
          total: uploaded + nextQueue.length,
          uploaded,
          failed: 0,
          remaining: nextQueue.length,
          failedRetryable: 0,
          lastError: "",
          updatedAt: Date.now(),
        },
      });
      await chrome.alarms.create(ALARM_NAME, { periodInMinutes: 1 });
      processQueue();
      sendResponse({ ok: true, total: failedQueue.length, queued: nextQueue.length });
    })().catch((error) => sendResponse({ ok: false, error: error.message || String(error) }));
    return true;
  }
  if (message?.type === "getUploadStatus") {
    storageGet([STATUS_KEY, QUEUE_KEY, FAILED_KEY])
      .then((stored) => {
        const status = stored[STATUS_KEY] || {};
        const failedQueue = stored[FAILED_KEY] || [];
        sendResponse({
          ok: true,
          status: {
            running: Boolean(status.running),
            total: Number(status.total || 0),
            uploaded: Number(status.uploaded || 0),
            failed: Number(status.failed || 0),
            remaining: (stored[QUEUE_KEY] || []).length,
            failedRetryable: failedQueue.length,
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
