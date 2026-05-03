const state = {
  lastData: null,
};

const SENSOR_STALE_AFTER_MS = 2 * 60 * 1000;

const ids = {
  status: document.getElementById("systemStatus"),
  lastUpdated: document.getElementById("lastUpdated"),
  commandMessage: document.getElementById("commandMessage"),
  suggestionText: document.getElementById("suggestionText"),
  sensorBanner: document.getElementById("sensorBanner"),
  temperature: document.getElementById("temperature"),
  humidity: document.getElementById("humidity"),
  aqi: document.getElementById("aqi"),
  eco2: document.getElementById("eco2"),
  tvoc: document.getElementById("tvoc"),
  light: document.getElementById("light"),
  motion: document.getElementById("motion"),
  smoke: document.getElementById("smoke"),
  sound: document.getElementById("sound"),
};

function nested(source, keys, fallback = null) {
  for (const key of keys) {
    let current = source;
    let found = true;
    for (const part of key.split(".")) {
      if (current && Object.prototype.hasOwnProperty.call(current, part)) {
        current = current[part];
      } else {
        found = false;
        break;
      }
    }
    if (found && current !== null && current !== undefined && current !== "") {
      return current;
    }
  }
  return fallback;
}

function formatNumber(value, suffix = "", decimals = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "--";
  }
  return `${number.toFixed(decimals)}${suffix}`;
}

function formatTimestamp(value) {
  if (!value) {
    return null;
  }
  if (typeof value === "number") {
    return new Date(value).toLocaleString();
  }
  return String(value);
}

function timestampMs(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const asNumber = Number(value);
    if (Number.isFinite(asNumber)) {
      return asNumber;
    }
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function isSensorOnline(room) {
  const rawTimestamp = nested(room, ["sensor_timestamp_ms", "sensor_timestamp_iso"]);
  const lastSeenMs = timestampMs(rawTimestamp);
  const isFresh = lastSeenMs !== null && Date.now() - lastSeenMs <= SENSOR_STALE_AFTER_MS;
  return room.feed_online === true && isFresh;
}

function setMetric(id, value, mode = "normal") {
  const element = ids[id];
  element.textContent = value;
  const card = element.closest(".metric");
  card.classList.remove("metric-offline", "metric-warning", "metric-good");
  if (mode !== "normal") {
    card.classList.add(`metric-${mode}`);
  }
}

function setSensorBanner(mode, text) {
  ids.sensorBanner.textContent = text;
  ids.sensorBanner.className = `sensor-banner sensor-banner-${mode}`;
}

function yesNo(value, yesText, noText) {
  if (value === true || value === 1 || value === "1" || value === "true") {
    return yesText;
  }
  if (value === false || value === 0 || value === "0" || value === "false") {
    return noText;
  }
  return "--";
}

function setStatus(mode, text) {
  ids.status.textContent = text;
  ids.status.className = `status-pill status-${mode}`;
}

function updateSensors(dashboard) {
  const room = dashboard.room || {};
  const sensorOnline = isSensorOnline(room);
  const temperature = nested(room, ["temperature"]);
  const humidity = nested(room, ["humidity"]);
  const aqi = nested(room, ["aqi"]);
  const eco2 = nested(room, ["eco2"]);
  const tvoc = nested(room, ["tvoc"]);
  const lightStatus = nested(room, ["light_status"]);
  const lightRaw = nested(room, ["light_raw"]);
  const motionText = nested(room, ["motion_text"]);
  const motion = nested(room, ["motion"]);
  const smokeText = nested(room, ["smoke_text"]);
  const smoke = nested(room, ["smoke"]);
  const noiseText = nested(room, ["noise_text"]);
  const noise = nested(room, ["noise"]);
  const soundRaw = nested(room, ["sound_level"]);
  const updated =
    formatTimestamp(nested(room, ["sensor_timestamp_iso", "sensor_timestamp_ms"])) ||
    nested(dashboard, ["updated_at_iso"]) ||
    "Unknown";

  if (!sensorOnline) {
    setSensorBanner("offline", `Sensor feed offline. Last reading: ${updated}`);
    setMetric("temperature", "Offline", "offline");
    setMetric("humidity", "Offline", "offline");
    setMetric("aqi", "Offline", "offline");
    setMetric("eco2", "Offline", "offline");
    setMetric("tvoc", "Offline", "offline");
    setMetric("light", "Offline", "offline");
    setMetric("motion", "Offline", "offline");
    setMetric("smoke", "Offline", "offline");
    setMetric("sound", "Offline", "offline");
    ids.lastUpdated.textContent = updated;
    return;
  }

  setSensorBanner("online", "Live ESP32 sensor feed is updating.");
  setMetric("temperature", formatNumber(temperature, " C"), Number(temperature) > 27 ? "warning" : "good");
  setMetric("humidity", formatNumber(humidity, " %"), "good");
  setMetric("aqi", aqi ?? "--", Number(aqi) > 3 ? "warning" : "good");
  setMetric("eco2", formatNumber(eco2, " ppm", 0), Number(eco2) > 1000 ? "warning" : "good");
  setMetric("tvoc", formatNumber(tvoc, " ppb", 0), Number(tvoc) > 220 ? "warning" : "good");
  setMetric("light", lightStatus || (lightRaw !== null ? String(lightRaw) : "--"), "normal");
  setMetric("motion", motionText || yesNo(motion, "Motion", "No motion"), "normal");
  setMetric("smoke", smokeText || yesNo(smoke, "Detected", "Clear"), smoke === true || smoke === 1 ? "warning" : "good");
  setMetric("sound", noiseText || yesNo(noise, "Noise", soundRaw !== null ? String(soundRaw) : "Quiet"), "normal");
  ids.lastUpdated.textContent = updated;
}

function breakerStatus(device) {
  const status = nested(device, ["state", "status.switch", "switch", "isOn", "on"]);
  const relay = nested(device, ["status.relay_status", "relay_status"]);
  if (status === true || status === "true" || status === "on" || relay === "on") {
    return "ON";
  }
  if (status === false || status === "false" || status === "off" || relay === "off") {
    return "OFF";
  }
  return "Unknown";
}

function updateBreakers(devices) {
  for (const id of ["breaker_01", "breaker_02"]) {
    const element = document.getElementById(`${id}_status`);
    const status = breakerStatus(devices[id] || {});
    element.textContent = status;
    element.style.background = status === "ON" ? "#dff5eb" : status === "OFF" ? "#ffe5e5" : "#edf2f0";
    element.style.color = status === "ON" ? "#157a4f" : status === "OFF" ? "#c63434" : "#66736d";
  }
}

function updateSuggestions(dashboard) {
  const room = dashboard.room || {};
  const sensorOnline = isSensorOnline(room);
  const smoke = nested(room, ["smoke"], 0);
  const smokeText = String(nested(room, ["smoke_text"], "")).toLowerCase();
  const eco2 = Number(nested(room, ["eco2"], 0));
  const motion = nested(room, ["motion"], null);
  const lightRaw = Number(nested(room, ["light_raw"], 0));
  const lightText = String(nested(room, ["light_status"], "")).toLowerCase();
  const recommendations = dashboard.recommendations || [];

  if (!sensorOnline) {
    ids.suggestionText.textContent = "The ESP32 sensor feed is offline. Check ESP32 power, Wi-Fi, and the Pi receiver service.";
  } else if (smoke === 1 || smoke === true || smokeText.includes("detect")) {
    ids.suggestionText.textContent = "Warning: smoke or gas detected. Check the room immediately.";
  } else if (recommendations.length > 0 && recommendations[0].message) {
    ids.suggestionText.textContent = recommendations[0].message;
  } else if (eco2 >= 1000) {
    ids.suggestionText.textContent = "eCO2 is high. Ventilate the room or open a window.";
  } else if ((motion === 0 || motion === false) && (lightRaw >= 1000 || lightText.includes("bright"))) {
    ids.suggestionText.textContent = "No motion is detected while the room is bright. Consider turning off lights.";
  } else {
    ids.suggestionText.textContent = "System looks normal. Sensor readings are being updated.";
  }
}

async function fetchLatest() {
  try {
    const response = await fetch("/api/latest", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Failed to load latest data");
    }

    const dashboard = data.dashboard || data;
    state.lastData = dashboard;
    setStatus("online", "Online");
    updateSensors(dashboard);
    updateBreakers(dashboard.devices || {});
    updateSuggestions(dashboard);
  } catch (error) {
    setStatus("error", "Error");
    ids.commandMessage.textContent = error.message;
  }
}

async function sendCommand(deviceId, action) {
  ids.commandMessage.textContent = "Sending command...";
  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        device_id: deviceId,
        action,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Command failed");
    }
    ids.commandMessage.textContent = `${deviceId} command sent`;
    await fetchLatest();
  } catch (error) {
    ids.commandMessage.textContent = `Command failed: ${error.message}`;
  }
}

document.querySelectorAll("[data-device-id][data-action]").forEach((button) => {
  button.addEventListener("click", () => {
    sendCommand(button.dataset.deviceId, button.dataset.action);
  });
});

fetchLatest();
setInterval(fetchLatest, 2000);
