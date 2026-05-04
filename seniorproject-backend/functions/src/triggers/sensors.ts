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
  setAlertActiveOrResolve,
} from "../alerts";
import { resolveRecommendation, upsertRecommendation } from "../recommendations";
import { handleSuggestedAction } from "../control";
import { msToIso, nowTimestamp } from "../utils";

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

      // Immediate safety alert
      if (log.smoke === 1) {
        await setAlertActiveOrResolve(backendRef, {
          alertKey: "smoke_detected",
          isActive: true,
          createInput: {
            type: "safety",
            subtype: "smoke_detected",
            level: "critical",
            message: "Smoke detected",
            source: "sensor_analysis",
            source_log: logId,
          },
          timestampMs: now,
        });

        setRecommendation("Check the room immediately for smoke or gas", 100);
      } else {
        await setAlertActiveOrResolve(backendRef, {
          alertKey: "smoke_detected",
          isActive: false,
          timestampMs: now,
        });
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
