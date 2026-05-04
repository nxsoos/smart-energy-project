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
      const noMotion = log.motion === 0;
      const motionDetected = log.motion === 1;

      const highTemp =
        typeof log.temperature === "number" &&
        log.temperature >= HIGH_TEMP_THRESHOLD;

      const soundRaw =
        typeof log.sound_raw === "number" ? log.sound_raw : null;
      const noise =
        typeof log.noise === "number" ? log.noise : null;
      const noiseText =
        typeof log.noise_text === "string" ? log.noise_text : null;
      const acousticPresence =
        noise === 1 || (noiseText?.toLowerCase() === "noise");
      const appearsEmpty = noMotion && !acousticPresence;

      let recommendation = "No recommendation";
      let recommendationPriority = 0;
      let wasteRisk = "low";
      let occupancyState = "unknown";

      const setRecommendation = (nextRecommendation: string, priority: number) => {
        if (priority >= recommendationPriority) {
          recommendation = nextRecommendation;
          recommendationPriority = priority;
        }
      };

      if (motionDetected) {
        occupancyState = "occupied";
      } else if (acousticPresence) {
        occupancyState = "possibly_occupied";
      } else if (noMotion) {
        occupancyState = "possibly_empty";
      }

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
      if (isBright && appearsEmpty) {
        const pendingSnap = await lightNoMotionPendingRef.get();

        if (!pendingSnap.exists()) {
          const pending: PendingCondition = {
            active: true,
            started_at: now,
            last_seen_at: now,
            alert_sent: false,
            type: "light_on_no_motion",
            source_log: logId,
          };

          await lightNoMotionPendingRef.set(pending);
        } else {
          await lightNoMotionPendingRef.update({
            active: true,
            last_seen_at: now,
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
            active: true,
            started_at: now,
            last_seen_at: now,
            alert_sent: false,
            type: "high_temperature",
            source_log: logId,
          };

          await highTempPendingRef.set(pending);
        } else {
          await highTempPendingRef.update({
            active: true,
            last_seen_at: now,
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
        lastSeenMs: measurementTimestampMs,
      });

      await currentStateRef.set({
        last_log_id: logId,
        last_processed_at: now,
        occupancy_state: occupancyState,
        waste_risk: wasteRisk,
        recommendation,
        latest_temperature: log.temperature ?? null,
        latest_humidity: log.humidity ?? null,
        latest_sound_raw: soundRaw,
        noise,
        noise_text: noiseText,
        motion: log.motion ?? null,
        light_status: log.light_status ?? null,
        smoke: log.smoke ?? null,
      });

      await backendRef.child("dashboard/environment").set({
        updated_at: now,

        temperature: log.temperature ?? null,
        humidity: log.humidity ?? null,
        sound_raw: soundRaw,
        noise,
        noise_text: noiseText,
        motion: log.motion ?? null,
        light_status: log.light_status ?? null,
        smoke: log.smoke ?? null,

        occupancy_state: occupancyState,
        waste_risk: wasteRisk,
        recommendation,

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
          const duration = now - lightCondition.started_at;

          if (duration >= LIGHT_NO_MOTION_DELAY_MS) {
            await createOrUpdateActiveAlert(
              backendRef,
              "light_on_no_motion",
              {
                type: "energy_waste",
                subtype: "light_on_no_motion",
                level: "medium",
                message: "Lights may be on while the room appears empty.",
                source: "sensor_analysis",
                source_log: lightCondition.source_log ?? null,
                additionalFields: {
                  started_at: lightCondition.started_at,
                  duration_ms: duration,
                },
              },
              now
            );

            await pendingRef.child("light_on_no_motion").update({
              alert_sent: true,
              alert_sent_at: now,
            });

            await currentStateRef.update({
              waste_risk: "medium",
              recommendation:
                "Turn off the lights if the room is actually empty.",
              last_alert_type: "energy_waste",
              last_alert_at: now,
            });

            await upsertRecommendation(
              backendRef,
              "light_on_no_motion",
              {
                type: "energy_saving",
                priority: "medium",
                title: "Possible energy waste",
                message: "Turn off the lights if the room is actually empty.",
                source: "backend_analysis",
                related_alert_key: "light_on_no_motion",
              },
              now
            );

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

        const tempCondition =
          pendingConditions.high_temperature as PendingCondition | undefined;

        if (
          tempCondition &&
          tempCondition.active
        ) {
          const duration = now - tempCondition.started_at;

          if (duration >= HIGH_TEMP_DELAY_MS) {
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
              alert_sent: true,
              alert_sent_at: now,
            });

            await currentStateRef.update({
              recommendation:
                "Consider turning on cooling or adjusting the AC setting.",
              last_alert_type: "comfort",
              last_alert_at: now,
            });

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
