import { admin } from "./firebase";
import { DEVICE_OFFLINE_AFTER_MS } from "./config";
import type { DeviceHealthStatus } from "./types";
import { createOrUpdateActiveAlert, markAlertResolving, resolveAlertToHistory } from "./alerts";
import { msToIso } from "./utils";

export async function checkAndUpdateDeviceHealth(
  homeId: string,
  deviceId: string,
  timestampMs: number
): Promise<{
  online: boolean;
  health_status: DeviceHealthStatus;
  lastSeenMs: number | null;
  offline_since: number | null;
}> {
  const backendRef = admin.database().ref(`/homes/${homeId}/backend`);
  const deviceStatusRef = admin
    .database()
    .ref(`/homes/${homeId}/devices/${deviceId}/status`);

  const statusSnap = await deviceStatusRef.get();
  const settingsSnap = await admin.database().ref(`/homes/${homeId}/settings`).get();
  const settings =
    settingsSnap.exists() && typeof settingsSnap.val() === "object" && settingsSnap.val() !== null
      ? (settingsSnap.val() as Record<string, unknown>)
      : {};
  const offlineAfterMs =
    typeof settings.device_offline_minutes === "number" && settings.device_offline_minutes > 0
      ? settings.device_offline_minutes * 60 * 1000
      : DEVICE_OFFLINE_AFTER_MS;
  const status = statusSnap.exists()
    ? (statusSnap.val() as Record<string, unknown>)
    : {};

  const lastSeenMsRaw =
    typeof status.lastSeenMs === "number"
      ? status.lastSeenMs
      : typeof status.last_seen_ms === "number"
      ? status.last_seen_ms
      : typeof status.last_seen_at === "number"
      ? status.last_seen_at
      : null;

  const alertKey = `device_offline_${deviceId}`;
  const isBreaker = deviceId.startsWith("breaker_");
  const tuyaOnline =
    typeof status.online === "boolean" ? (status.online as boolean) : null;

  let online = false;
  let healthStatus: DeviceHealthStatus = "unknown";
  let offlineSince =
    typeof status.offline_since === "number" ? status.offline_since : null;

  if (isBreaker && tuyaOnline !== null) {
    online = tuyaOnline;
    healthStatus = tuyaOnline ? "online" : "offline";
    offlineSince = tuyaOnline ? null : offlineSince ?? timestampMs;

    if (tuyaOnline) {
      await markAlertResolving(backendRef, alertKey, timestampMs);
      await resolveAlertToHistory(backendRef, alertKey, timestampMs);
    } else {
      await createOrUpdateActiveAlert(
        backendRef,
        alertKey,
        {
          type: "device_health",
          subtype: "device_offline",
          level: "high",
          message: `${deviceId} is offline according to Tuya Cloud.`,
          source: "device_health_monitor",
          additionalFields: {
            device_id: deviceId,
            lastSeenMs: lastSeenMsRaw,
            offline_since: offlineSince,
          },
        },
        timestampMs
      );
    }
  } else if (typeof lastSeenMsRaw !== "number") {
    healthStatus = "unknown";
    online = false;
    offlineSince = offlineSince ?? timestampMs;

    await createOrUpdateActiveAlert(
      backendRef,
      alertKey,
      {
        type: "device_health",
        subtype: "device_offline",
        level: "high",
        message: `${deviceId} has no last seen timestamp.`,
        source: "device_health_monitor",
        additionalFields: {
          device_id: deviceId,
          offline_since: offlineSince,
        },
      },
      timestampMs
    );
  } else if (timestampMs - lastSeenMsRaw > offlineAfterMs) {
    healthStatus = "offline";
    online = false;
    offlineSince = offlineSince ?? timestampMs;

    await createOrUpdateActiveAlert(
      backendRef,
      alertKey,
      {
        type: "device_health",
        subtype: "device_offline",
        level: "high",
        message: `${deviceId} appears offline.`,
        source: "device_health_monitor",
        additionalFields: {
          device_id: deviceId,
          lastSeenMs: lastSeenMsRaw,
          offline_since: offlineSince,
        },
      },
      timestampMs
    );
  } else {
    healthStatus = "online";
    online = true;
    offlineSince = null;

    await markAlertResolving(backendRef, alertKey, timestampMs);
    await resolveAlertToHistory(backendRef, alertKey, timestampMs);
  }

  const statusUpdates: Record<string, unknown> = {
    health_status: healthStatus,
    lastSeenMs: lastSeenMsRaw,
    last_seen_ms: lastSeenMsRaw,
    last_seen_iso: msToIso(lastSeenMsRaw),
    last_health_check_at: timestampMs,
    last_health_check_at_ms: timestampMs,
    last_health_check_at_iso: msToIso(timestampMs),
    offline_since: offlineSince,
    offline_since_ms: offlineSince,
    offline_since_iso: msToIso(offlineSince),
  };
  if (!isBreaker || tuyaOnline === null) {
    statusUpdates.online = online;
  }

  await deviceStatusRef.update(statusUpdates);

  return {
    online,
    health_status: healthStatus,
    lastSeenMs: lastSeenMsRaw,
    offline_since: offlineSince,
  };
}
