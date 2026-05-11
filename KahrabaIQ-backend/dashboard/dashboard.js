const fmt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
let statePollTimer = null;
let iotSocket = null;
let mqttPacketId = 1;

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function setStatus(label, mode = "ok") {
  text("statusText", label);
  const dot = document.getElementById("statusDot");
  dot.className = `dot ${mode === "warn" ? "warn" : mode === "error" ? "error" : ""}`;
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.success === false) throw new Error(data.detail || data.message || "Request failed");
  return data;
}

function renderBootstrap(data) {
  text("subtitle", data.paired ? `${data.home_id} - live cloud dashboard` : "Pi is online, waiting for pairing");
  document.getElementById("pairingPanel").hidden = data.paired;
  document.getElementById("dashboardGrid").hidden = !data.paired;
  if (!data.paired) {
    setStatus("Waiting for pairing", "warn");
    text("pairPiId", data.pi_id || "--");
    text("pairWifi", data.pi?.wifi_ssid || "--");
    text("pairPublicIp", data.public_ip || "--");
    return;
  }
  setStatus("Live", "ok");
  renderState(data.latest_state || {});
}

function deviceState(device) {
  if (device.online === false) return "offline";
  return device.display_state || device.state || "unknown";
}

function renderState(data) {
  const dashboard = data.dashboard || data;
  const energy = dashboard.energy || data.energy || {};
  const room = dashboard.room || data.room || {};
  const devices = dashboard.devices || data.devices || {};
  const deviceList = Object.entries(devices).map(([id, value]) => ({ id, ...(value || {}) })).filter((device) => {
    const type = String(device.type || "");
    return type !== "esp32_sensor" && !String(device.id || "").startsWith("esp32");
  });
  const breakers = deviceList.filter((device) => String(device.type || "").includes("breaker"));
  const activeBreakers = breakers.filter((device) => deviceState(device) === "on").length;

  text("power", fmt.format(number(energy.currentPowerW ?? energy.powerW ?? energy.current_power_w ?? energy.total_power_W)));
  text("energyToday", `${fmt.format(number(energy.energyTodayKwh ?? energy.totalEnergyKwh ?? energy.today_kwh ?? energy.total_energy_kWh))} kWh`);
  text("costToday", `${number(energy.costToday ?? energy.today_cost_bhd ?? energy.total_cost_BHD).toFixed(3)} BD`);
  text("breakerCount", `${activeBreakers}/${breakers.length || 0}`);
  text("temperature", room.online === false ? "Offline" : `${fmt.format(number(room.temperature))} C`);
  text("humidity", room.online === false ? "Offline" : `${fmt.format(number(room.humidity))} %`);
  text("motion", room.motion_text || (number(room.motion) ? "Motion" : "Clear"));
  text("smoke", room.smoke_text || (number(room.smoke) ? "Detected" : "Clear"));

  const devicesNode = document.getElementById("devices");
  devicesNode.innerHTML = "";
  if (!deviceList.length) {
    devicesNode.textContent = "No device data yet.";
  } else {
    for (const device of deviceList) {
      const state = deviceState(device);
      const card = document.createElement("div");
      card.className = "device";
      card.innerHTML = `
        <div class="device-head">
          <div><div class="device-name">${device.name || device.id || "Device"}</div><div class="label">${device.branch || device.control_method || ""}</div></div>
          <div class="state ${state === "offline" || state === "failed" ? state : ""}">${state}</div>
        </div>
        <div class="device-metrics">
          <div>Power<strong>${fmt.format(number(device.power_W ?? device.power_w))} W</strong></div>
          <div>Energy<strong>${fmt.format(number(device.energy_kWh ?? device.energy_kwh))} kWh</strong></div>
          <div>Voltage<strong>${fmt.format(number(device.voltage_V ?? device.voltage_v))} V</strong></div>
          <div>Current<strong>${fmt.format(number(device.current_A ?? device.current_a))} A</strong></div>
        </div>`;
      devicesNode.appendChild(card);
    }
  }

  const alerts = dashboard.alerts || data.alerts || [];
  const aiNotifications = dashboard.ai_notifications || data.ai_notifications || [];
  const notes = [];
  for (const alert of alerts) notes.push(`<span class="error">${alert.title || alert.message || "Active alert"}</span>`);
  for (const notification of aiNotifications.slice(0, 3)) notes.push(`<span class="warn">${notification.title || notification.message || "Notification"}</span>`);
  document.getElementById("alerts").innerHTML = notes.length ? notes.join("<br>") : "No active alerts.";
}

function encodeString(value) {
  const encoded = new TextEncoder().encode(value);
  return [encoded.length >> 8, encoded.length & 255, ...encoded];
}

function encodeRemainingLength(length) {
  const bytes = [];
  do {
    let digit = length % 128;
    length = Math.floor(length / 128);
    if (length > 0) digit |= 128;
    bytes.push(digit);
  } while (length > 0);
  return bytes;
}

function mqttPacket(type, variableAndPayload) {
  return new Uint8Array([type, ...encodeRemainingLength(variableAndPayload.length), ...variableAndPayload]);
}

function mqttConnectPacket(clientId) {
  const variable = [...encodeString("MQTT"), 4, 2, 0, 45];
  return mqttPacket(0x10, [...variable, ...encodeString(clientId)]);
}

function mqttSubscribePacket(topic) {
  const packetId = mqttPacketId++;
  const variable = [packetId >> 8, packetId & 255];
  return mqttPacket(0x82, [...variable, ...encodeString(topic), 0]);
}

function parsePublish(buffer) {
  const bytes = new Uint8Array(buffer);
  const type = bytes[0] >> 4;
  if (type !== 3) return null;
  let multiplier = 1;
  let value = 0;
  let index = 1;
  let encodedByte;
  do {
    encodedByte = bytes[index++];
    value += (encodedByte & 127) * multiplier;
    multiplier *= 128;
  } while ((encodedByte & 128) !== 0);
  const topicLength = (bytes[index] << 8) + bytes[index + 1];
  index += 2 + topicLength;
  const payload = new TextDecoder().decode(bytes.slice(index, index + value - topicLength - 2));
  return JSON.parse(payload);
}

async function connectIotLive() {
  const live = await getJson("/api/dashboard/iot/live-config");
  if (!live.paired || !live.config) return;
  const config = live.config;
  iotSocket = new WebSocket(config.signedUrl, ["mqtt"]);
  iotSocket.binaryType = "arraybuffer";
  iotSocket.onopen = () => iotSocket.send(mqttConnectPacket(config.clientId));
  iotSocket.onmessage = (event) => {
    const bytes = new Uint8Array(event.data);
    const packetType = bytes[0] >> 4;
    if (packetType === 2) {
      iotSocket.send(mqttSubscribePacket(config.topic));
      document.getElementById("liveMode").textContent = "AWS IoT live";
      return;
    }
    const payload = parsePublish(event.data);
    if (payload) renderState(payload);
  };
  iotSocket.onerror = () => document.getElementById("liveMode").textContent = "Live unavailable, polling";
  iotSocket.onclose = () => document.getElementById("liveMode").textContent = "Polling fallback";
}

async function pollState() {
  try {
    const data = await getJson("/api/dashboard/state");
    if (data.paired) renderState(data.state || {});
  } catch (error) {
    setStatus("Offline", "error");
    const notice = document.getElementById("notice");
    notice.hidden = false;
    notice.textContent = error.message;
  }
}

async function start() {
  try {
    const bootstrap = await getJson("/api/dashboard/bootstrap");
    renderBootstrap(bootstrap);
    if (bootstrap.paired) {
      connectIotLive().catch(() => document.getElementById("liveMode").textContent = "Polling fallback");
      statePollTimer = setInterval(pollState, 3000);
    } else {
      statePollTimer = setInterval(async () => renderBootstrap(await getJson("/api/dashboard/bootstrap")), 5000);
    }
  } catch (error) {
    setStatus("Blocked", "error");
    const notice = document.getElementById("notice");
    notice.hidden = false;
    notice.textContent = error.message;
    document.getElementById("dashboardGrid").hidden = true;
  }
}

window.addEventListener("beforeunload", () => {
  if (statePollTimer) clearInterval(statePollTimer);
  if (iotSocket) iotSocket.close();
});

start();
