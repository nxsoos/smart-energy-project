import { onValueCreated } from "firebase-functions/v2/database";
import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import { admin } from "../firebase";
import {
  DATABASE_INSTANCE,
  DATABASE_REGION,
  HIGH_TEMP_DELAY_MS,
  HIGH_TEMP_THRESHOLD,
  LIGHT_NO_MOTION_DELAY_MS,
} from "../config";
import type { PendingCondition } from "../types";
import {
  createOrUpdateActiveAlert,
  markAlertResolving,
  resolveAlertToHistory,
} from "../alerts";
import { resolveRecommendation, upsertRecommendation } from "../recommendations";
import { handleSuggestedAction } from "../control";
import { msToIso, nowTimestamp } from "../utils";

const SMOKE_ALERT_ID = "smoke_detected_room1";
const SMOKE_CONFIRMATION_COUNT = 2;
const SMOKE_CONFIRMATION_MS = 7000;
const SMOKE_CLEAR_DELAY_MS = 15000;

function asRecord(value: unknown): Record<string, any> {
  return typeof value === "object" && value !== null ? (value as Record<string, any>) : {};
}

function normalizeBool(value: unknown): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    return ["true", "1", "yes", "on", "detected", "smoke"].includes(value.trim().toLowerCase());
  }
  return false;
}

function defaultDeviceSafety(deviceId: string): Record<string, boolean> {
  if (deviceId === "breaker_01") {
    return { critical_device: false, emergency_shutdown_allowed: true, auto_shutdown_on_smoke: true };
  }
  if (deviceId === "breaker_02") {
    return { critical_device: false, emergency_shutdown_allowed: true, auto_shutdown_on_smoke: false };
  }
  return { critical_device: true, emergency_shutdown_allowed: false, auto_shutdown_on_smoke: false };
}

async function writeSafetyEvent(
  homeId: string,
  type: string,
  message: string,
  actionsTaken: string[] = [],
  timestampMs = Date.now()
): Promise<void> {
  const eventId = `safety_${timestampMs}_${type}`;
  await admin.database().ref(`/homes/${homeId}/safety/events/${eventId}`).set({
    ...nowTimestamp(timestampMs),
    event_id: eventId,
    type,
    severity: type.includes("confirmed") || type.includes("emergency") ? "critical" : "medium",
    message,
    source: "mq2",
    actions_taken: actionsTaken,
    created_at_ms: timestampMs,
    created_at_iso: msToIso(timestampMs),
  });
}

async function createEmergencySuggestion(
  homeId: string,
  deviceId: string,
  deviceName: string,
  reason: string,
  timestampMs: number
): Promise<void> {
  const suggestionId = `smoke_emergency_${deviceId}`;
  const ref = admin.database().ref(`/homes/${homeId}/action_suggestions/active/${suggestionId}`);
  const snap = await ref.get();
  if (snap.exists()) {
    return;
  }
  await ref.set({
    ...nowTimestamp(timestampMs),
    suggestion_id: suggestionId,
    type: "emergency_action",
    severity: "critical",
    home_id: homeId,
    device_id: deviceId,
    device_name: deviceName,
    suggested_command: "turn_off",
    target_state: "off",
    reason,
    source: "safety_rule",
    status: "waiting_for_user",
    created_at_ms: timestampMs,
    created_at_iso: msToIso(timestampMs),
    actions: ["approve", "dismiss"],
  });
}

async function createNotification(homeId: string, timestampMs: number): Promise<void> {
  const notificationId = `notif_${timestampMs}`;
  const notification = {
    ...nowTimestamp(timestampMs),
    notification_id: notificationId,
    type: "critical_alert",
    alert_type: "smoke_detected",
    severity: "critical",
    title: "Smoke/Gas Detected",
    body: "Smoke or gas was detected in Room 1. Check immediately.",
    home_id: homeId,
    room_id: "room1",
    read: false,
    delivered: false,
    created_at_ms: timestampMs,
    created_at_iso: msToIso(timestampMs),
  };
  await admin.database().ref(`/homes/${homeId}/notifications/${notificationId}`).set(notification);

  const tokens = asRecord(
    (await admin.database().ref(`/homes/${homeId}/notification_tokens`).get()).val()
  );
  const activeTokens = Object.values(tokens)
    .map((item) => asRecord(item))
    .filter((item) => item.active === true && typeof item.token === "string")
    .map((item) => item.token as string);
  if (!activeTokens.length) {
    return;
  }
  let delivered = false;
  for (const token of activeTokens) {
    try {
      await admin.messaging().send({
        token,
        notification: { title: notification.title, body: notification.body },
        data: {
          home_id: homeId,
          notification_id: notificationId,
          alert_type: "smoke_detected",
          severity: "critical",
        },
      });
      delivered = true;
    } catch (error) {
      logger.warn("Failed to send smoke notification", { homeId, error });
    }
  }
  if (delivered) {
    await admin.database().ref(`/homes/${homeId}/notifications/${notificationId}`).update({
      delivered: true,
      delivered_at_ms: Date.now(),
      delivered_at_iso: msToIso(Date.now()),
    });
  }
}

async function createEmergencyCommand(
  homeId: string,
  deviceId: string,
  deviceName: string,
  timestampMs: number
): Promise<string> {
  const commandId = `cmd_${timestampMs}_${deviceId}`;
  const commandRecord = {
    ...nowTimestamp(timestampMs),
    command_id: commandId,
    home_id: homeId,
    device_id: deviceId,
    device_name: deviceName,
    command: "turn_off",
    action: "turn_off",
    target_state: "off",
    requested_by: "emergency_auto_shutdown",
    reason: "Smoke or gas emergency automatic shutdown for explicitly safe device.",
    source: "smoke_emergency",
    emergency: true,
    alert_id: SMOKE_ALERT_ID,
    status: "pending",
    requested_at_ms: timestampMs,
    requested_at_iso: msToIso(timestampMs),
    sent_at_ms: null,
    sent_at_iso: null,
    confirmed_at_ms: null,
    confirmed_at_iso: null,
    failed_at_ms: null,
    failed_at_iso: null,
    timeout_at_ms: null,
    timeout_at_iso: null,
    result: { success: null, actual_state: null, error_code: null, user_message: null, raw_error: null },
    retry_count: 0,
    max_retries: 1,
  };
  await admin.database().ref(`/homes/${homeId}`).update({
    [`commands/pending/${commandId}`]: commandRecord,
    [`commands/history/${commandId}`]: commandRecord,
    [`commands/latest_by_device/${deviceId}`]: commandRecord,
    [`commands/${deviceId}/latest`]: {
      ...commandRecord,
      created_at: timestampMs,
      created_at_ms: timestampMs,
      created_at_iso: msToIso(timestampMs),
      source: "smoke_emergency",
    },
    [`devices/${deviceId}/command_in_progress`]: true,
    [`devices/${deviceId}/pending_command_id`]: commandId,
    [`devices/${deviceId}/pending_target_state`]: "off",
    [`devices/${deviceId}/last_requested_state`]: "off",
    [`devices/${deviceId}/last_command_status`]: "pending",
    [`devices/${deviceId}/last_command_message`]: "Emergency shutdown command accepted.",
    [`automation_logs/auto_${timestampMs}_${deviceId}`]: {
      log_id: `auto_${timestampMs}_${deviceId}`,
      home_id: homeId,
      device_id: deviceId,
      device_name: deviceName,
      command: "turn_off",
      target_state: "off",
      reason: "Smoke or gas emergency automatic shutdown.",
      command_id: commandId,
      source: "smoke_emergency",
      created_at_ms: timestampMs,
      created_at_iso: msToIso(timestampMs),
    },
  });
  return commandId;
}

async function confirmSmokeEmergency(homeId: string, logId: string, timestampMs: number): Promise<void> {
  const homeRef = admin.database().ref(`/homes/${homeId}`);
  const existingAlert = await homeRef.child(`alerts/active/${SMOKE_ALERT_ID}`).get();
  const alert = {
    ...nowTimestamp(timestampMs),
    alert_id: SMOKE_ALERT_ID,
    alert_type: "smoke_detected",
    category: "safety",
    severity: "critical",
    status: "active",
    title: "Smoke/Gas Detected",
    message: "Smoke or gas was detected in Room 1. Check the area immediately.",
    room_id: "room1",
    source: "mq2",
    source_log: logId,
    requires_user_attention: true,
    created_at_ms: existingAlert.exists()
      ? asRecord(existingAlert.val()).created_at_ms ?? timestampMs
      : timestampMs,
    created_at_iso: existingAlert.exists()
      ? asRecord(existingAlert.val()).created_at_iso ?? msToIso(timestampMs)
      : msToIso(timestampMs),
    updated_at_ms: timestampMs,
    updated_at_iso: msToIso(timestampMs),
  };
  await homeRef.child(`alerts/active/${SMOKE_ALERT_ID}`).set(alert);
  if (!existingAlert.exists()) {
    await homeRef.child(`alerts/history/alert_${timestampMs}_${SMOKE_ALERT_ID}`).set({
      ...alert,
      event: "created",
    });
  }
  await homeRef.child("safety/emergency_mode").set({
    ...nowTimestamp(timestampMs),
    active: true,
    reason: "smoke_detected",
    severity: "critical",
    started_at_ms: timestampMs,
    started_at_iso: msToIso(timestampMs),
    ended_at_ms: null,
    ended_at_iso: null,
    message: "Smoke or gas was detected. Normal automation is paused.",
    updated_at_ms: timestampMs,
    updated_at_iso: msToIso(timestampMs),
  });

  const emergencyTasks = [
    createNotification(homeId, timestampMs),
    writeSafetyEvent(homeId, "smoke_confirmed", "Smoke or gas was confirmed in Room 1.", [
      "critical_alert_created",
      "emergency_mode_enabled",
      "notification_created",
      "popup_required",
    ], timestampMs),
  ];
  if (!existingAlert.exists()) {
    emergencyTasks.push(
      createEmergencySuggestion(
        homeId,
        "breaker_01",
        "Switch Breaker",
        "Smoke or gas was detected. Turning off this breaker may reduce electrical risk.",
        timestampMs
      ),
      createEmergencySuggestion(
        homeId,
        "breaker_02",
        "AC Breaker",
        "Smoke or gas was detected. Turning off AC/fan simulation may help prevent spreading smoke or gas.",
        timestampMs
      )
    );
  }
  await Promise.all(emergencyTasks);

  const control = asRecord((await homeRef.child("control").get()).val());
  if (String(control.mode ?? "assist").toLowerCase() !== "auto") {
    return;
  }
  const devices = asRecord((await homeRef.child("devices").get()).val());
  for (const deviceId of Object.keys(devices)) {
    const device = asRecord(devices[deviceId]);
    const safetySnap = await homeRef.child(`devices/${deviceId}/safety`).get();
    const safety = { ...defaultDeviceSafety(deviceId), ...asRecord(safetySnap.val()) };
    await homeRef.child(`devices/${deviceId}/safety`).update(safety);
    if (safety.emergency_shutdown_allowed !== true || safety.auto_shutdown_on_smoke !== true) {
      continue;
    }
    if (normalizeBool(device.command_in_progress)) {
      continue;
    }
    const status = asRecord(device.status);
    const online = normalizeBool(status.online);
    const isOn = normalizeBool(status.switch) || String(status.state ?? "").toLowerCase() === "on";
    if (online === false || !isOn) {
      continue;
    }
    const commandId = await createEmergencyCommand(
      homeId,
      deviceId,
      String(device.name ?? (deviceId === "breaker_01" ? "Switch Breaker" : "AC Breaker")),
      timestampMs + Object.keys(devices).indexOf(deviceId)
    );
    await writeSafetyEvent(homeId, "emergency_shutdown_command_created", `Auto Mode created ${commandId}.`, [
      "auto_shutdown_on_smoke",
      deviceId,
    ]);
  }
}

async function handleSmokeConfirmation(homeId: string, logId: string, smokeDetected: boolean, timestampMs: number): Promise<void> {
  const smokeRef = admin.database().ref(`/homes/${homeId}/safety/smoke_state`);
  const current = asRecord((await smokeRef.get()).val());
  if (smokeDetected) {
    const firstDetectedAt =
      current.status === "pending" || current.status === "confirmed"
        ? Number(current.first_detected_at_ms ?? timestampMs)
        : timestampMs;
    const consecutive = Number(current.consecutive_detections ?? 0) + 1;
    const confirmed =
      consecutive >= SMOKE_CONFIRMATION_COUNT ||
      timestampMs - firstDetectedAt >= SMOKE_CONFIRMATION_MS ||
      current.status === "confirmed";
    await smokeRef.set({
      ...nowTimestamp(timestampMs),
      status: confirmed ? "confirmed" : "pending",
      consecutive_detections: consecutive,
      first_detected_at_ms: firstDetectedAt,
      first_detected_at_iso: msToIso(firstDetectedAt),
      last_detected_at_ms: timestampMs,
      last_detected_at_iso: msToIso(timestampMs),
      last_clear_at_ms: null,
      last_clear_at_iso: null,
      updated_at_ms: timestampMs,
      updated_at_iso: msToIso(timestampMs),
    });
    await writeSafetyEvent(
      homeId,
      confirmed ? "smoke_confirmed" : "smoke_pending",
      confirmed ? "Smoke or gas was confirmed in Room 1." : "Smoke or gas detection is pending confirmation.",
      confirmed ? ["confirmation_threshold_met"] : [],
      timestampMs
    );
    if (confirmed) {
      await confirmSmokeEmergency(homeId, logId, timestampMs);
    }
    return;
  }

  const lastClearAt =
    typeof current.last_clear_at_ms === "number" ? current.last_clear_at_ms : timestampMs;
  const remainsConfirmedDuringClearDelay = current.status === "confirmed" && timestampMs - lastClearAt < SMOKE_CLEAR_DELAY_MS;
  await smokeRef.set({
    ...nowTimestamp(timestampMs),
    status: remainsConfirmedDuringClearDelay ? "confirmed" : "clear",
    consecutive_detections: 0,
    first_detected_at_ms: remainsConfirmedDuringClearDelay ? current.first_detected_at_ms ?? null : null,
    first_detected_at_iso: remainsConfirmedDuringClearDelay ? current.first_detected_at_iso ?? null : null,
    last_detected_at_ms: current.last_detected_at_ms ?? null,
    last_detected_at_iso: current.last_detected_at_iso ?? null,
    last_clear_at_ms: lastClearAt,
    last_clear_at_iso: msToIso(lastClearAt),
    updated_at_ms: timestampMs,
    updated_at_iso: msToIso(timestampMs),
  });

  if (current.status === "pending") {
    await writeSafetyEvent(homeId, "smoke_cleared", "Smoke/gas cleared before confirmation.", [], timestampMs);
    return;
  }
  if (current.status === "confirmed" && timestampMs - lastClearAt >= SMOKE_CLEAR_DELAY_MS) {
    const homeRef = admin.database().ref(`/homes/${homeId}`);
    const alertSnap = await homeRef.child(`alerts/active/${SMOKE_ALERT_ID}`).get();
    if (alertSnap.exists()) {
      await homeRef.child(`alerts/history/alert_${timestampMs}_${SMOKE_ALERT_ID}`).set({
        ...asRecord(alertSnap.val()),
        ...nowTimestamp(timestampMs),
        status: "resolved",
        resolved_at_ms: timestampMs,
        resolved_at_iso: msToIso(timestampMs),
        updated_at_ms: timestampMs,
        updated_at_iso: msToIso(timestampMs),
      });
      await homeRef.child(`alerts/active/${SMOKE_ALERT_ID}`).remove();
    }
    await homeRef.child("safety/emergency_mode").update({
      active: false,
      ended_at_ms: timestampMs,
      ended_at_iso: msToIso(timestampMs),
      updated_at_ms: timestampMs,
      updated_at_iso: msToIso(timestampMs),
    });
    await writeSafetyEvent(homeId, "emergency_mode_disabled", "Smoke/gas cleared after safe delay.", [
      "critical_alert_resolved",
      "normal_automation_resumed",
    ], timestampMs);
  }
}

export const analyzeSensorLog = onValueCreated(
  {
    ref: "/homes/{homeId}/history/sensor_logs/{logId}",
    instance: DATABASE_INSTANCE,
    region: DATABASE_REGION,
  },
  async (event) => {
    try {
      const snapshot = event.data;

      if (!snapshot) {
        logger.info("No snapshot data found.");
        return;
      }

      const log = snapshot.val();
      const { homeId, logId } = event.params;
      const now = Date.now();
      const measurementTimestampMs =
        typeof log.timestamp_ms === "number" ? log.timestamp_ms : now;

      const backendRef = admin.database().ref(`/homes/${homeId}/backend`);
      const occupancySnap = await admin
        .database()
        .ref(`/homes/${homeId}/occupancy/room1`)
        .get();
      const occupancy =
        occupancySnap.exists() && typeof occupancySnap.val() === "object" && occupancySnap.val() !== null
          ? (occupancySnap.val() as Record<string, unknown>)
          : {};
      const settingsSnap = await admin.database().ref(`/homes/${homeId}/settings`).get();
      const settings =
        settingsSnap.exists() && typeof settingsSnap.val() === "object" && settingsSnap.val() !== null
          ? (settingsSnap.val() as Record<string, unknown>)
          : {};
      const highTempThreshold =
        typeof settings.high_temperature_threshold === "number"
          ? settings.high_temperature_threshold
          : HIGH_TEMP_THRESHOLD;
      const breakerSnap = await admin
        .database()
        .ref(`/homes/${homeId}/devices/breaker_01/status`)
        .get();
      const breakerStatus =
        breakerSnap.exists() && typeof breakerSnap.val() === "object" && breakerSnap.val() !== null
          ? (breakerSnap.val() as Record<string, unknown>)
          : {};
      const currentStateRef = backendRef.child("current_state");
      const esp32StatusRef = admin
        .database()
        .ref(`/homes/${homeId}/devices/esp32_01/status`);

      const lightNoMotionPendingRef = backendRef.child(
        "pending_conditions/light_on_no_motion"
      );

      const highTempPendingRef = backendRef.child(
        "pending_conditions/high_temperature"
      );

      const isBright = log.light_status === "Bright";
      const breakerOn =
        breakerStatus.switch === true ||
        breakerStatus.state === "on" ||
        breakerStatus.switch_state === "on";
      const noMotion = log.motion === 0;
      const motionDetected = log.motion === 1;

      const highTemp =
        typeof log.temperature === "number" &&
        log.temperature >= highTempThreshold;

      const soundRaw =
        typeof log.sound_raw === "number" ? log.sound_raw : null;
      const noise =
        typeof log.noise === "number" ? log.noise : null;
      const noiseText =
        typeof log.noise_text === "string" ? log.noise_text : null;
      const acousticPresence =
        noise === 1 || (noiseText?.toLowerCase() === "noise");
      const occupancyState =
        typeof occupancy.state === "string" ? occupancy.state : "unknown";
      const occupancyAppearsEmpty =
        occupancyState === "empty" || occupancyState === "probably_empty";
      const appearsEmpty =
        occupancyState === "unknown" ? noMotion && !acousticPresence : occupancyAppearsEmpty;

      let recommendation = "No recommendation";
      let recommendationPriority = 0;
      let wasteRisk = "low";
      let fallbackOccupancyState = "unknown";

      const setRecommendation = (nextRecommendation: string, priority: number) => {
        if (priority >= recommendationPriority) {
          recommendation = nextRecommendation;
          recommendationPriority = priority;
        }
      };

      if (motionDetected) {
        fallbackOccupancyState = "occupied";
      } else if (acousticPresence) {
        fallbackOccupancyState = "probably_occupied";
      } else if (noMotion) {
        fallbackOccupancyState = "probably_empty";
      }
      const currentOccupancyState =
        occupancyState === "unknown" ? fallbackOccupancyState : occupancyState;

      // MQ2 smoke/gas safety handling uses confirmation before critical alert.
      const smokeDetected =
        normalizeBool(log.smoke) ||
        normalizeBool(log.smoke_text) ||
        normalizeBool(log.smoke_status);
      await handleSmokeConfirmation(homeId, logId, smokeDetected, now);
      if (smokeDetected) {
        setRecommendation("Check the room immediately for smoke or gas", 100);
      }

      // Start/update light + no motion pending condition
      if (appearsEmpty && (isBright || breakerOn)) {
        const pendingSnap = await lightNoMotionPendingRef.get();

        if (!pendingSnap.exists()) {
          const pending: PendingCondition = {
            ...nowTimestamp(now),
            active: true,
            started_at: now,
            started_at_ms: now,
            started_at_iso: msToIso(now),
            last_seen_at: now,
            last_seen_ms: now,
            last_seen_iso: msToIso(now),
            alert_sent: false,
            type: "light_on_no_motion",
            light_on: isBright,
            breaker_on: breakerOn,
            source_log: logId,
          };

          await lightNoMotionPendingRef.set(pending);
        } else {
          await lightNoMotionPendingRef.update({
            ...nowTimestamp(now),
            active: true,
            last_seen_at: now,
            last_seen_ms: now,
            last_seen_iso: msToIso(now),
            light_on: isBright,
            breaker_on: breakerOn,
            source_log: logId,
          });
        }

        wasteRisk = "possible";
        setRecommendation(
          "Monitoring possible lighting waste. Waiting before creating an alert.",
          10
        );
      } else {
        const pendingSnap = await lightNoMotionPendingRef.get();

        if (pendingSnap.exists()) {
          await lightNoMotionPendingRef.remove();
          await resolveRecommendation(backendRef, "light_on_no_motion", now);
        }

        await markAlertResolving(backendRef, "light_on_no_motion", now);
        await resolveAlertToHistory(backendRef, "light_on_no_motion", now);
      }

      // Start/update high temperature pending condition
      if (highTemp) {
        const pendingSnap = await highTempPendingRef.get();

        if (!pendingSnap.exists()) {
          const pending: PendingCondition = {
            ...nowTimestamp(now),
            active: true,
            started_at: now,
            started_at_ms: now,
            started_at_iso: msToIso(now),
            last_seen_at: now,
            last_seen_ms: now,
            last_seen_iso: msToIso(now),
            alert_sent: false,
            type: "high_temperature",
            source_log: logId,
          };

          await highTempPendingRef.set(pending);
        } else {
          await highTempPendingRef.update({
            ...nowTimestamp(now),
            active: true,
            last_seen_at: now,
            last_seen_ms: now,
            last_seen_iso: msToIso(now),
            source_log: logId,
          });
        }

        setRecommendation(
          "Monitoring high room temperature before creating an alert.",
          20
        );
      } else {
        const pendingSnap = await highTempPendingRef.get();

        if (pendingSnap.exists()) {
          await highTempPendingRef.remove();
          await resolveRecommendation(backendRef, "comfort_high_temperature", now);
        }

        await markAlertResolving(backendRef, "high_temperature", now);
        await resolveAlertToHistory(backendRef, "high_temperature", now);
      }

      await esp32StatusRef.update({
        ...nowTimestamp(measurementTimestampMs),
        lastSeenMs: measurementTimestampMs,
        last_seen_ms: measurementTimestampMs,
        last_seen_iso: msToIso(measurementTimestampMs),
      });

      await currentStateRef.set({
        ...nowTimestamp(now),
        last_log_id: logId,
        last_processed_at: now,
        last_processed_at_ms: now,
        last_processed_at_iso: msToIso(now),
        occupancy_state: currentOccupancyState,
        occupied: occupancy.occupied ?? null,
        occupancy_confidence: occupancy.confidence ?? null,
        occupancy_reason: occupancy.reason ?? null,
        waste_risk: wasteRisk,
        recommendation,
        latest_temperature: log.temperature ?? null,
        latest_humidity: log.humidity ?? null,
        latest_sound_raw: soundRaw,
        comfort_temperature_min:
          typeof settings.comfort_temperature_min === "number"
            ? settings.comfort_temperature_min
            : null,
        comfort_temperature_max:
          typeof settings.comfort_temperature_max === "number"
            ? settings.comfort_temperature_max
            : null,
        high_temperature_threshold: highTempThreshold,
        noise,
        noise_text: noiseText,
        motion: log.motion ?? null,
        light_status: log.light_status ?? null,
        smoke: log.smoke ?? null,
      });

      await backendRef.child("dashboard/environment").set({
        ...nowTimestamp(now),
        updated_at: now,
        updated_at_ms: now,
        updated_at_iso: msToIso(now),

        temperature: log.temperature ?? null,
        humidity: log.humidity ?? null,
        sound_raw: soundRaw,
        noise,
        noise_text: noiseText,
        motion: log.motion ?? null,
        light_status: log.light_status ?? null,
        smoke: log.smoke ?? null,

        occupancy_state: currentOccupancyState,
        occupied: occupancy.occupied ?? null,
        occupancy_confidence: occupancy.confidence ?? null,
        occupancy_reason: occupancy.reason ?? null,
        waste_risk: wasteRisk,
        recommendation,
        comfort_temperature_min:
          typeof settings.comfort_temperature_min === "number"
            ? settings.comfort_temperature_min
            : null,
        comfort_temperature_max:
          typeof settings.comfort_temperature_max === "number"
            ? settings.comfort_temperature_max
            : null,
        high_temperature_threshold: highTempThreshold,

        last_log_id: logId,
      });

      logger.info("Sensor log processed successfully", { homeId, logId });
    } catch (error) {
      logger.error("Error processing sensor log", error);
    }
  }
);

export const checkPendingConditions = onSchedule(
  {
    schedule: "every 1 minutes",
    region: DATABASE_REGION,
    timeZone: "Asia/Bahrain",
  },
  async () => {
    try {
      const now = Date.now();

      const homesRef = admin.database().ref("/homes");
      const homesSnap = await homesRef.get();

      if (!homesSnap.exists()) {
        logger.info("No homes found.");
        return;
      }

      const homes = homesSnap.val();

      for (const homeId of Object.keys(homes)) {
        const backendRef = admin.database().ref(`/homes/${homeId}/backend`);
        const pendingRef = backendRef.child("pending_conditions");
        const currentStateRef = backendRef.child("current_state");
        const settingsSnap = await admin.database().ref(`/homes/${homeId}/settings`).get();
        const settings =
          settingsSnap.exists() && typeof settingsSnap.val() === "object" && settingsSnap.val() !== null
            ? (settingsSnap.val() as Record<string, unknown>)
            : {};
        const lightDelayMs =
          typeof settings.light_waste_minutes === "number" && settings.light_waste_minutes > 0
            ? settings.light_waste_minutes * 60 * 1000
            : LIGHT_NO_MOTION_DELAY_MS;
        const highTempDelayMs =
          HIGH_TEMP_DELAY_MS;
        const aiRecommendationsEnabled = settings.ai_recommendations_enabled !== false;

        const pendingSnap = await pendingRef.get();

        if (!pendingSnap.exists()) {
          continue;
        }

        const pendingConditions = pendingSnap.val();

        const lightCondition =
          pendingConditions.light_on_no_motion as PendingCondition | undefined;

        if (
          lightCondition &&
          lightCondition.active
        ) {
          const occupancySnap = await admin
            .database()
            .ref(`/homes/${homeId}/occupancy/room1`)
            .get();
          const occupancy =
            occupancySnap.exists() && typeof occupancySnap.val() === "object" && occupancySnap.val() !== null
              ? (occupancySnap.val() as Record<string, unknown>)
              : {};
          const occupancyState =
            typeof occupancy.state === "string" ? occupancy.state : "unknown";
          const roomLooksEmpty =
            occupancyState === "empty" || occupancyState === "probably_empty";
          if (!roomLooksEmpty) {
            await pendingRef.child("light_on_no_motion").remove();
          } else {
            const duration = now - lightCondition.started_at;

            if (duration >= lightDelayMs) {
            await createOrUpdateActiveAlert(
              backendRef,
              "light_on_no_motion",
              {
                type: "energy_waste",
                subtype: "light_on_no_motion",
                level: "medium",
                message: "Light or switch breaker may be on while the room appears empty.",
                source: "sensor_analysis",
                source_log: lightCondition.source_log ?? null,
                additionalFields: {
                  started_at: lightCondition.started_at,
                  duration_ms: duration,
                  light_on: lightCondition.light_on ?? null,
                  breaker_on: lightCondition.breaker_on ?? null,
                },
              },
              now
            );

            await pendingRef.child("light_on_no_motion").update({
              ...nowTimestamp(now),
              alert_sent: true,
              alert_sent_at: now,
              alert_sent_at_ms: now,
              alert_sent_at_iso: msToIso(now),
            });

            await currentStateRef.update({
              ...nowTimestamp(now),
              waste_risk: "medium",
              recommendation:
                "Turn off Switch Breaker if the room is actually empty.",
              last_alert_type: "energy_waste",
              last_alert_at: now,
              last_alert_at_ms: now,
              last_alert_at_iso: msToIso(now),
            });

            if (aiRecommendationsEnabled) {
              await upsertRecommendation(
                backendRef,
                "light_on_no_motion",
                {
                  type: "energy_saving",
                  priority: "medium",
                  title: "Possible energy waste",
                  message: "The room appears empty and Switch Breaker is still on.",
                  source: "backend_analysis",
                  related_alert_key: "light_on_no_motion",
                  related_device_id: "breaker_01",
                },
                now
              );
            }

            await handleSuggestedAction(homeId, {
              deviceId: "breaker_01",
              deviceName: "Switch Breaker",
              command: "turn_off",
              reason: "Light is on while the room appears empty.",
              source: "backend_analysis",
            });

            logger.info("Created scheduled light/no-motion alert", {
              homeId,
              duration_ms: duration,
            });
            }
          }
        }

        const tempCondition =
          pendingConditions.high_temperature as PendingCondition | undefined;

        if (
          tempCondition &&
          tempCondition.active
        ) {
          const duration = now - tempCondition.started_at;

          if (duration >= highTempDelayMs) {
            await createOrUpdateActiveAlert(
              backendRef,
              "high_temperature",
              {
                type: "comfort",
                subtype: "high_temperature",
                level: "medium",
                message: "High room temperature detected for more than 5 minutes",
                source: "sensor_analysis",
                source_log: tempCondition.source_log ?? null,
                additionalFields: {
                  started_at: tempCondition.started_at,
                  duration_ms: duration,
                },
              },
              now
            );

            await pendingRef.child("high_temperature").update({
              ...nowTimestamp(now),
              alert_sent: true,
              alert_sent_at: now,
              alert_sent_at_ms: now,
              alert_sent_at_iso: msToIso(now),
            });

            await currentStateRef.update({
              ...nowTimestamp(now),
              recommendation:
                "Consider turning on cooling or adjusting the AC setting.",
              last_alert_type: "comfort",
              last_alert_at: now,
              last_alert_at_ms: now,
              last_alert_at_iso: msToIso(now),
            });

            if (aiRecommendationsEnabled) {
              await upsertRecommendation(
                backendRef,
                "comfort_high_temperature",
                {
                  type: "comfort",
                  priority: "medium",
                  title: "Room temperature is high",
                  message:
                    "Consider turning on cooling or adjusting the AC setting.",
                  source: "backend_analysis",
                  related_alert_key: "high_temperature",
                },
                now
              );
            }

            await handleSuggestedAction(homeId, {
              deviceId: "breaker_02",
              deviceName: "AC Breaker",
              command: "turn_on",
              reason: "Room temperature is high and cooling may improve comfort.",
              source: "backend_analysis",
            });

            logger.info("Created scheduled high-temperature alert", {
              homeId,
              duration_ms: duration,
            });
          }
        }
      }

      logger.info("Scheduled pending-condition check completed.");
    } catch (error) {
      logger.error("Error checking pending conditions", error);
    }
  }
);
