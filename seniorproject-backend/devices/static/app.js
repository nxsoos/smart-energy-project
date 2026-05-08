const state = { lastData: null, smokeEmergencyDismissed: false, smokeClearStartedAt: null, showPairingQr: false };
const SENSOR_STALE_AFTER_MS = 2 * 60 * 1000;

const ids = {
  status: document.getElementById("systemStatus"),
  cloudStatus: document.getElementById("cloudStatus"),
  piIdentity: document.getElementById("piIdentity"),
  pairingScreen: document.getElementById("pairingScreen"),
  dashboardScreen: document.getElementById("dashboardScreen"),
  pairingPayload: document.getElementById("pairingPayload"),
  pairingQr: document.getElementById("pairingQr"),
  pairingQrFallback: document.getElementById("pairingQrFallback"),
  showPairingQr: document.getElementById("showPairingQr"),
  pairEsp32: document.getElementById("pairEsp32"),
  esp32Modal: document.getElementById("esp32Modal"),
  esp32Form: document.getElementById("esp32Form"),
  esp32Message: document.getElementById("esp32Message"),
  esp32Ssid: document.getElementById("esp32Ssid"),
  esp32Password: document.getElementById("esp32Password"),
  esp32SetupUrl: document.getElementById("esp32SetupUrl"),
  esp32Cancel: document.getElementById("esp32Cancel"),
  esp32Discover: document.getElementById("esp32Discover"),
  lastUpdated: document.getElementById("lastUpdated"),
  commandMessage: document.getElementById("commandMessage"),
  suggestionText: document.getElementById("suggestionText"),
  sensorBanner: document.getElementById("sensorBanner"),
  occupancyState: document.getElementById("occupancyState"),
  occupancyReason: document.getElementById("occupancyReason"),
  temperature: document.getElementById("temperature"),
  humidity: document.getElementById("humidity"),
  powerNow: document.getElementById("powerNow"),
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
  nextSchedule: document.getElementById("nextSchedule"),
  emergencyOverlay: document.getElementById("emergencyOverlay"),
  emergencyMessage: document.getElementById("emergencyMessage"),
  adminModal: document.getElementById("adminModal"),
  adminMessage: document.getElementById("adminMessage"),
};

function nested(source, keys, fallback = null) {
  for (const key of keys) {
    let current = source;
    let found = true;
    for (const part of key.split(".")) {
      if (current && Object.prototype.hasOwnProperty.call(current, part)) current = current[part];
      else { found = false; break; }
    }
    if (found && current !== null && current !== undefined && current !== "") return current;
  }
  return fallback;
}

function formatNumber(value, suffix = "", decimals = 1) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(decimals)}${suffix}` : "--";
}

function setStatus(element, mode, text) {
  if (!element) return;
  element.textContent = text;
  element.className = `status-chip ${mode}`;
}

function timestampMs(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const asNumber = Number(value);
    if (Number.isFinite(asNumber)) return asNumber;
    const parsed = Date.parse(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function isSensorOnline(room) {
  const raw = nested(room, ["sensor_timestamp_ms", "timestamp_ms", "last_seen_ms", "sensor_timestamp_iso", "timestamp_iso"]);
  const seen = timestampMs(raw);
  return (seen !== null && Date.now() - seen <= SENSOR_STALE_AFTER_MS) || room.feed_online === true;
}

function updateKioskState(data) {
  ids.piIdentity.textContent = `${data.pi_id || "Pi"} · ${data.home_id || "unpaired"}`;
  setStatus(ids.cloudStatus, data.cloud_enabled ? "online" : "muted", data.cloud_status || "Local");
  if (data.paired && !state.showPairingQr) {
    ids.pairingScreen.classList.add("hidden");
    ids.dashboardScreen.classList.remove("hidden");
  } else {
    ids.dashboardScreen.classList.add("hidden");
    ids.pairingScreen.classList.remove("hidden");
    ids.pairingPayload.textContent = data.pairing_payload || "Waiting for pairing token";
    if (data.pairing_qr_data_url) {
      ids.pairingQr.src = data.pairing_qr_data_url;
      ids.pairingQr.classList.remove("hidden");
      ids.pairingQrFallback.classList.add("hidden");
    } else {
      ids.pairingQr.classList.add("hidden");
      ids.pairingQrFallback.classList.remove("hidden");
    }
  }
  if (ids.showPairingQr) ids.showPairingQr.textContent = state.showPairingQr ? "Hide QR" : "Pair QR";
  if (ids.esp32Ssid && data.wifi_ssid && !ids.esp32Ssid.value) ids.esp32Ssid.value = data.wifi_ssid;
  if (ids.pairEsp32) {
    const linked = data.esp32 && (data.esp32.ip || data.esp32.base_url);
    ids.pairEsp32.textContent = linked ? "ESP32 Linked" : "Pair ESP32";
    ids.pairEsp32.className = `status-chip ${linked ? "online" : "muted"}`;
  }
}

async function fetchKioskState() {
  const response = await fetch("/api/kiosk/state", { cache: "no-store" });
  const data = await response.json();
  if (response.ok && data.success) updateKioskState(data);
}

function updateSensors(dashboard) {
  const room = dashboard.room || {};
  const occupancy = dashboard.occupancy || {};
  const online = isSensorOnline(room);
  const updated = nested(room, ["sensor_timestamp_iso", "timestamp_iso", "sensor_timestamp_ms"], dashboard.updated_at_iso || "Unknown");
  ids.occupancyState.textContent = String(occupancy.state || room.occupancy_state || "Unknown").replaceAll("_", " ");
  ids.occupancyReason.textContent = occupancy.reason || room.occupancy_reason || "Waiting for occupancy analysis.";
  ids.sensorBanner.textContent = online ? "Live ESP32 sensor feed is updating." : `Sensor feed offline. Last reading: ${updated}`;
  ids.temperature.textContent = formatNumber(nested(room, ["temperature"]), " C");
  ids.humidity.textContent = formatNumber(nested(room, ["humidity"]), " %");
  ids.aqi.textContent = nested(room, ["aqi"], "--");
  ids.eco2.textContent = formatNumber(nested(room, ["eco2"]), " ppm", 0);
  ids.tvoc.textContent = formatNumber(nested(room, ["tvoc"]), " ppb", 0);
  ids.light.textContent = nested(room, ["light_status", "light_raw"], "--");
  ids.motion.textContent = nested(room, ["motion_text"], nested(room, ["motion"], false) ? "Motion" : "No motion");
  ids.smoke.textContent = nested(room, ["smoke_text"], nested(room, ["smoke"], false) ? "Detected" : "Clear");
  ids.sound.textContent = nested(room, ["noise_text", "sound_level", "noise"], "--");
  ids.lastUpdated.textContent = String(updated);
}

function breakerStatus(device) {
  const status = nested(device, ["display_state", "state", "status.switch", "switch", "isOn", "on"]);
  const relay = nested(device, ["status.relay_status", "relay_status"]);
  if (status === true || status === "true" || status === "on" || relay === "on") return "ON";
  if (status === false || status === "false" || status === "off" || relay === "off") return "OFF";
  return "Unknown";
}

function updateBreakers(devices) {
  for (const id of ["breaker_01", "breaker_02", "matter_socket_switch", "matter_ac_switch"]) {
    const device = devices[id] || {};
    const element = document.getElementById(`${id}_status`);
    const card = document.querySelector(`.device-tile[data-device-id="${id}"]`);
    const buttons = document.querySelectorAll(`button[data-device-id="${id}"]`);
    if (!element || !card) continue;
    const inProgress = nested(device, ["command_in_progress"], false) === true;
    const localControl = nested(device, ["control_method"], "") === "home_assistant";
    const online = nested(device, ["online"], false) === true && (!localControl || nested(device, ["local_online"], false) === true);
    const controllable = nested(device, ["controllable"], true) !== false;
    const status = breakerStatus(device);
    element.textContent = !online ? "Offline" : !controllable ? "Disabled" : inProgress ? `${status} · Processing` : status;
    element.style.color = status === "ON" ? "var(--primary)" : status === "OFF" ? "var(--danger)" : "var(--muted)";
    buttons.forEach((button) => { button.disabled = inProgress || !online || !controllable; });
  }
}

function updateSuggestions(dashboard) {
  const room = dashboard.room || {};
  const recommendations = dashboard.recommendations || [];
  const smokeText = String(nested(room, ["smoke_text"], "")).toLowerCase();
  if (nested(room, ["smoke"], false) || smokeText.includes("detect")) ids.suggestionText.textContent = "Warning: smoke or gas detected. Check the room immediately.";
  else if (recommendations.length && recommendations[0].message) ids.suggestionText.textContent = recommendations[0].message;
  else ids.suggestionText.textContent = "System looks normal. Sensor readings are being updated.";
}

function updateControlMode(dashboard) {
  const control = dashboard.control || {};
  ids.controlModeLabel.textContent = control.label || "Assist";
  ids.controlModeDescription.textContent = control.description || "Assist mode";
}

function activeSmokeEmergency(dashboard) {
  const safety = dashboard.safety || {};
  const room = dashboard.room || {};
  const smoke = nested(room, ["smoke"], false);
  const smokeText = String(nested(room, ["smoke_text"], "")).toLowerCase();
  if (smoke === true || smoke === 1 || smokeText.includes("detect")) return { message: "Smoke or gas was detected. Check immediately." };
  const emergency = safety.emergency_mode || {};
  if (emergency.active === true) return { message: emergency.message || "Emergency mode is active." };
  return null;
}

function updateEmergencyOverlay(dashboard) {
  const alert = activeSmokeEmergency(dashboard);
  if (!alert || state.smokeEmergencyDismissed) ids.emergencyOverlay.classList.add("hidden");
  else { ids.emergencyMessage.textContent = alert.message; ids.emergencyOverlay.classList.remove("hidden"); }
}

async function fetchLatest() {
  try {
    const response = await fetch("/api/latest", { cache: "no-store" });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.message || "Failed to load latest data");
    const dashboard = data.dashboard || data;
    state.lastData = dashboard;
    setStatus(ids.status, "online", "Online");
    ids.powerNow.textContent = formatNumber(nested(dashboard, ["energy.current_power_w", "energy.total_power_W"], 0), " W", 0);
    updateSensors(dashboard);
    updateBreakers(dashboard.devices || {});
    updateSuggestions(dashboard);
    updateControlMode(dashboard);
    updateEmergencyOverlay(dashboard);
  } catch (error) {
    setStatus(ids.status, "error", "Error");
    ids.commandMessage.textContent = error.message;
  }
}

async function postAction(path, body = null) {
  const response = await fetch(path, { method: "POST", headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : null });
  const data = await response.json();
  if (!response.ok || data.success === false) throw new Error(data.message || data.detail || "Action failed");
  ids.commandMessage.textContent = data.message || "Action requested.";
  await fetchLatest();
}

async function postJson(path, body = {}) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok || data.success === false) throw new Error(data.message || data.detail || "Action failed");
  return data;
}

async function sendCommand(deviceId, action) {
  ids.commandMessage.textContent = "Processing command...";
  try { await postAction("/api/command", { device_id: deviceId, action }); }
  catch (error) { ids.commandMessage.textContent = `Command failed: ${error.message}`; }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item === tab));
    document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === tab.dataset.tab));
  });
});

document.querySelectorAll("[data-device-id][data-action]").forEach((button) => button.addEventListener("click", () => sendCommand(button.dataset.deviceId, button.dataset.action)));
document.getElementById("emergencyAllOff").addEventListener("click", () => { state.smokeEmergencyDismissed = true; ids.emergencyOverlay.classList.add("hidden"); postAction("/api/safety/smoke/actions/turn-off-safe-devices").catch((error) => { ids.commandMessage.textContent = error.message; }); });
document.getElementById("emergencyMarkSafe").addEventListener("click", () => { state.smokeEmergencyDismissed = true; ids.emergencyOverlay.classList.add("hidden"); postAction("/api/safety/smoke/actions/mark-safe").catch((error) => { ids.commandMessage.textContent = error.message; }); });
if (ids.showPairingQr) ids.showPairingQr.addEventListener("click", () => { state.showPairingQr = !state.showPairingQr; fetchKioskState().catch(() => {}); });
if (ids.pairEsp32) ids.pairEsp32.addEventListener("click", () => { ids.esp32Modal.classList.remove("hidden"); fetchKioskState().catch(() => {}); });
if (ids.esp32Cancel) ids.esp32Cancel.addEventListener("click", () => ids.esp32Modal.classList.add("hidden"));
if (ids.esp32Discover) ids.esp32Discover.addEventListener("click", async () => {
  ids.esp32Message.textContent = "Searching for ESP32 on this network...";
  try {
    const data = await postJson("/api/esp32/discover");
    ids.esp32Message.textContent = data.message || "ESP32 linked.";
    await fetchKioskState();
  } catch (error) { ids.esp32Message.textContent = error.message; }
});
if (ids.esp32Form) ids.esp32Form.addEventListener("submit", async (event) => {
  event.preventDefault();
  ids.esp32Message.textContent = "Sending Wi-Fi credentials to ESP32...";
  try {
    const data = await postJson("/api/esp32/provision", {
      ssid: ids.esp32Ssid.value,
      password: ids.esp32Password.value,
      setup_url: ids.esp32SetupUrl.value,
    });
    ids.esp32Password.value = "";
    ids.esp32Message.textContent = data.message || "Credentials sent. Wait 10 seconds, then tap Discover.";
  } catch (error) { ids.esp32Message.textContent = error.message; }
});

let adminTapCount = 0;
document.getElementById("adminHotspot").addEventListener("click", () => {
  adminTapCount += 1;
  if (adminTapCount >= 5) { ids.adminModal.classList.remove("hidden"); adminTapCount = 0; }
  setTimeout(() => { adminTapCount = 0; }, 2000);
});
document.getElementById("adminCancel").addEventListener("click", () => ids.adminModal.classList.add("hidden"));
document.getElementById("adminForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const password = document.getElementById("adminPassword").value;
    await postAction("/api/kiosk/unlock", { password });
    ids.adminMessage.textContent = "Unlocked. Use OS kiosk controls to exit during prototype.";
  } catch (error) { ids.adminMessage.textContent = error.message; }
});

fetchKioskState().catch(() => {});
fetchLatest();
setInterval(fetchKioskState, 30000);
setInterval(fetchLatest, 2000);
