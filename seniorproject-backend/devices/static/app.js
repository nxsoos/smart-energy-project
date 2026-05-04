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
  controlModeLabel: document.getElementById("controlModeLabel"),
  controlModeDescription: document.getElementById("controlModeDescription"),
  actionSuggestions: document.getElementById("actionSuggestions"),
  automationMessage: document.getElementById("automationMessage"),
  settingsModal: document.getElementById("settingsModal"),
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
  const status = nested(device, ["display_state", "state", "status.switch", "switch", "isOn", "on"]);
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
    const device = devices[id] || {};
    const element = document.getElementById(`${id}_status`);
    const card = document.querySelector(`.breaker[data-device-id="${id}"]`);
    const buttons = document.querySelectorAll(`button[data-device-id="${id}"]`);
    const inProgress = nested(device, ["command_in_progress"], false) === true;
    const online = nested(device, ["online"], false) === true;
    const controllable = nested(device, ["controllable"], true) !== false;
    const pendingTarget = nested(device, ["pending_target_state"], null);
    const lastCommand = nested(device, ["last_command.user_message", "last_command_message"], "");
    const status = breakerStatus(device);
    element.textContent = inProgress && pendingTarget ? `${status} - Processing` : status;
    element.style.background = status === "ON" ? "#dff5eb" : status === "OFF" ? "#ffe5e5" : "#edf2f0";
    element.style.color = status === "ON" ? "#157a4f" : status === "OFF" ? "#c63434" : "#66736d";
    card?.classList.toggle("breaker-pending", inProgress);
    card?.classList.toggle("breaker-disabled", !online || !controllable);
    buttons.forEach((button) => {
      button.disabled = inProgress || !online || !controllable;
    });
    if (!online) {
      element.textContent = "Offline";
    } else if (!controllable) {
      element.textContent = "Disabled";
    } else if (!inProgress && lastCommand) {
      element.title = lastCommand;
    }
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

function prettyCommand(command) {
  return command === "turn_off" ? "Turn Off" : "Turn On";
}

function updateControlMode(dashboard) {
  const control = dashboard.control || {};
  const label = control.label || "Assist";
  ids.controlModeLabel.textContent = `Mode: ${label}`;
  ids.controlModeDescription.textContent =
    control.description ||
    "The system suggests actions and asks before controlling devices.";
  document.querySelectorAll(".mode-option").forEach((button) => {
    button.classList.toggle("mode-selected", button.dataset.mode === control.mode);
  });
}

function updateActionSuggestionCards(dashboard) {
  const control = dashboard.control || {};
  const suggestions = Array.isArray(dashboard.action_suggestions)
    ? dashboard.action_suggestions
    : [];

  ids.actionSuggestions.innerHTML = "";
  if (control.mode !== "assist" || suggestions.length === 0) {
    return;
  }

  for (const suggestion of suggestions) {
    const card = document.createElement("article");
    card.className = "card action-suggestion";
    card.innerHTML = `
      <h2>${suggestion.device_name || "Device"} may be wasting energy.</h2>
      <p>${suggestion.reason || "Energy-saving action suggested."}</p>
      <div class="button-row">
        <button class="btn btn-on" data-suggestion-id="${suggestion.suggestion_id}" data-decision="approve">${prettyCommand(suggestion.suggested_command)}</button>
        <button class="btn btn-muted" data-suggestion-id="${suggestion.suggestion_id}" data-decision="dismiss">Dismiss</button>
      </div>
    `;
    ids.actionSuggestions.appendChild(card);
  }
}

function updateAutomationMessage(dashboard) {
  const control = dashboard.control || {};
  const logs = Array.isArray(dashboard.automation_logs)
    ? dashboard.automation_logs
    : [];
  ids.automationMessage.classList.add("hidden");
  ids.automationMessage.textContent = "";
  if (control.mode !== "auto" || logs.length === 0) {
    return;
  }
  const latest = [...logs].sort(
    (a, b) => Number(b.created_at_ms || 0) - Number(a.created_at_ms || 0)
  )[0];
  const action = latest.command === "turn_off" ? "turned off" : "turned on";
  ids.automationMessage.textContent = `Auto Mode ${action} ${latest.device_name || "Device"} because ${latest.reason || "an energy-saving rule matched."}`;
  ids.automationMessage.classList.remove("hidden");
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
    updateControlMode(dashboard);
    updateActionSuggestionCards(dashboard);
    updateAutomationMessage(dashboard);
  } catch (error) {
    setStatus("error", "Error");
    ids.commandMessage.textContent = error.message;
  }
}

async function changeMode(mode) {
  ids.commandMessage.textContent = "Updating control mode...";
  try {
    const response = await fetch("/api/control/mode", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ mode }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Control mode update failed");
    }
    ids.commandMessage.textContent = data.message || `Control mode changed to ${mode}.`;
    ids.settingsModal.classList.add("hidden");
    await fetchLatest();
  } catch (error) {
    ids.commandMessage.textContent = `Mode update failed: ${error.message}`;
  }
}

async function decideSuggestion(suggestionId, decision) {
  ids.commandMessage.textContent = "Updating suggestion...";
  try {
    const response = await fetch(`/api/action-suggestions/${suggestionId}/${decision}`, {
      method: "POST",
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Suggestion update failed");
    }
    ids.commandMessage.textContent = data.message || "Suggestion updated.";
    await fetchLatest();
  } catch (error) {
    ids.commandMessage.textContent = `Suggestion failed: ${error.message}`;
  }
}

async function sendCommand(deviceId, action) {
  const device = nested(state.lastData || {}, [`devices.${deviceId}`], {});
  const currentState = nested(device, ["display_state", "state"], "unknown");
  const targetState = action === "turn_on" ? "on" : "off";
  if (currentState === targetState && nested(device, ["command_in_progress"], false) !== true) {
    ids.commandMessage.textContent = `Already ${targetState}`;
    return;
  }

  ids.commandMessage.textContent = "Processing command...";
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
    ids.commandMessage.textContent = data.message || (data.no_action ? `Already ${targetState}` : "Command sent. Waiting for breaker confirmation.");
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

document.getElementById("settingsButton").addEventListener("click", () => {
  ids.settingsModal.classList.remove("hidden");
});

document.getElementById("closeSettingsButton").addEventListener("click", () => {
  ids.settingsModal.classList.add("hidden");
});

document.querySelectorAll(".mode-option").forEach((button) => {
  button.addEventListener("click", () => {
    changeMode(button.dataset.mode);
  });
});

ids.actionSuggestions.addEventListener("click", (event) => {
  const button = event.target.closest("[data-suggestion-id][data-decision]");
  if (!button) {
    return;
  }
  decideSuggestion(button.dataset.suggestionId, button.dataset.decision);
});

fetchLatest();
setInterval(fetchLatest, 2000);
