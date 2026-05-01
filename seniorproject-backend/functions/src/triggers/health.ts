import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import { admin } from "../firebase";
import { DATABASE_REGION } from "../config";
import { checkAndUpdateDeviceHealth } from "../deviceHealth";

export const checkDeviceHealth = onSchedule(
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
        logger.info("No homes found for device health check.");
        return;
      }

      const homes = homesSnap.val() as Record<string, unknown>;

      for (const homeId of Object.keys(homes)) {
        const deviceHealth: Record<string, unknown> = {};

        for (const deviceId of ["esp32_01", "breaker_01", "breaker_02"]) {
          const health = await checkAndUpdateDeviceHealth(homeId, deviceId, now);
          deviceHealth[deviceId] = {
            online: health.online,
            health_status: health.health_status,
            lastSeenMs: health.lastSeenMs,
            offline_since: health.offline_since,
          };
        }

        await admin
          .database()
          .ref(`/homes/${homeId}/backend/device_health`)
          .set({
            updated_at: now,
            devices: deviceHealth,
          });
      }

      logger.info("Device health check completed.");
    } catch (error) {
      logger.error("Error checking device health", error);
    }
  }
);
