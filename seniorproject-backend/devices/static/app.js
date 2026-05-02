const state = {
  lastData: null,
};

const ids = {
  status: document.getElementById("systemStatus"),
  lastUpdated: document.getElementById("lastUpdated"),
  commandMessage: document.getElementById("commandMessage"),
  suggestionText: document.getElementById("suggestionText"),
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

function updateSensors(esp32) {
  const temperature = nested(esp32, ["sensors.temperature", "temperature"]);
  const humidity = nested(esp32, ["sensors.humidity", "humidity"]);
  const aqi = nested(esp32, ["sensors.aqi", "aqi"]);
  const eco2 = nested(esp32, ["sensors.eco2", "sensors.eCO2", "eco2", "eCO2"]);
  const tvoc = nested(esp32, ["sensors.tvoc", "tvoc"]);
  const lightStatus = nested(esp32, ["sensors.light_status", "light_status"]);
  const lightRaw = nested(esp32, ["sensors.light_raw", "light_raw"]);
  const motionText = nested(esp32, ["sensors.motion_text", "motion_text"]);
  const motion = nested(esp32, ["sensors.motion", "motion"]);
  const smokeText = nested(esp32, ["sensors.smoke_text", "smoke_text"]);
  const smoke = nested(esp32, ["sensors.smoke", "smoke"]);
  const noiseText = nested(esp32, ["sensors.noise_text", "noise_text"]);
  const noise = nested(esp32, ["sensors.noise", "noise"]);
  const soundRaw = nested(esp32, ["sensors.sound_raw", "sound_raw"]);
  const updated =
    nested(esp32, ["timestamp", "sensors.readable_time", "status.readableTime"]) ||
    "Unknown";

  ids.temperature.textContent = formatNumber(temperature, " C");
  ids.humidity.textContent = formatNumber(humidity, " %");
  ids.aqi.textContent = aqi ?? "--";
  ids.eco2.textContent = formatNumber(eco2, " ppm", 0);
  ids.tvoc.textContent = formatNumber(tvoc, " ppb", 0);
  ids.light.textContent = lightStatus || (lightRaw !== null ? String(lightRaw) : "--");
  ids.motion.textContent = motionText || yesNo(motion, "Motion", "No motion");
  ids.smoke.textContent = smokeText || yesNo(smoke, "Detected", "Clear");
  ids.sound.textContent = noiseText || yesNo(noise, "Noise", soundRaw !== null ? String(soundRaw) : "Quiet");
  ids.lastUpdated.textContent = updated;
}

function breakerStatus(device) {
  const status = nested(device, ["status.switch", "switch", "isOn", "on"]);
  const relay = nested(device, ["status.relay_status", "relay_status"]);
  if (status === true || status === "true" || relay === "on") {
    return "ON";
  }
  if (status === false || status === "false" || relay === "off") {
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

function updateSuggestions(esp32) {
  const smoke = nested(esp32, ["sensors.smoke", "smoke"], 0);
  const smokeText = String(nested(esp32, ["sensors.smoke_text", "smoke_text"], "")).toLowerCase();
  const eco2 = Number(nested(esp32, ["sensors.eco2", "sensors.eCO2", "eco2", "eCO2"], 0));
  const motion = nested(esp32, ["sensors.motion", "motion"], null);
  const lightRaw = Number(nested(esp32, ["sensors.light_raw", "light_raw"], 0));
  const lightText = String(nested(esp32, ["sensors.light_status", "light_status"], "")).toLowerCase();

  if (smoke === 1 || smoke === true || smokeText.includes("detect")) {
    ids.suggestionText.textContent = "Warning: smoke or gas detected. Check the room immediately.";
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

    state.lastData = data;
    setStatus("online", "Online");
    updateSensors(data.esp32 || {});
    updateBreakers(data.devices || {});
    updateSuggestions(data.esp32 || {});
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
