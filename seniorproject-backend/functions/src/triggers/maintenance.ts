import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import { admin } from "../firebase";
import { DATABASE_REGION, ONE_DAY_MS, RAW_LOG_RETENTION_DAYS } from "../config";
import { cleanupPathByTimestamp } from "../cleanup";

export const cleanupOldRawLogs = onSchedule(
  {
    schedule: "0 3 * * *",
    region: DATABASE_REGION,
    timeZone: "Asia/Bahrain",
  },
  async () => {
    const now = Date.now();
    const cutoffMs = now - RAW_LOG_RETENTION_DAYS * ONE_DAY_MS;
    const runId = `cleanup_${now}`;

    try {
      const homesRef = admin.database().ref("/homes");
      const homesSnap = await homesRef.get();

      if (!homesSnap.exists()) {
        logger.info("No homes found for cleanup.");
        return;
      }

      const homes = homesSnap.val() as Record<string, unknown>;

      for (const homeId of Object.keys(homes)) {
        const startedAt = Date.now();
        const cleanupRunRef = admin
          .database()
          .ref(`/homes/${homeId}/backend/maintenance/cleanup_runs/${runId}`);
        const latestCleanupRef = admin
          .database()
          .ref(`/homes/${homeId}/backend/maintenance/latest_cleanup`);

        try {
          const updates: Record<string, null> = {};

          const deletedSensorLogs = await cleanupPathByTimestamp(
            homeId,
            "sensor_logs",
            cutoffMs,
            updates
          );

          const deletedBreaker1Logs = await cleanupPathByTimestamp(
            homeId,
            "breaker_01",
            cutoffMs,
            updates
          );

          const deletedBreaker2Logs = await cleanupPathByTimestamp(
            homeId,
            "breaker_02",
            cutoffMs,
            updates
          );

          if (Object.keys(updates).length > 0) {
            await admin.database().ref().update(updates);
          }

          const completedAt = Date.now();
          const summary = {
            run_id: runId,
            started_at: startedAt,
            completed_at: completedAt,
            cutoff_ms: cutoffMs,
            retention_days: RAW_LOG_RETENTION_DAYS,
            deleted: {
              sensor_logs: deletedSensorLogs,
              breaker_01: deletedBreaker1Logs,
              breaker_02: deletedBreaker2Logs,
            },
            status: "completed",
          };

          await cleanupRunRef.set(summary);
          await latestCleanupRef.set(summary);
        } catch (error) {
          const completedAt = Date.now();
          const errorMessage =
            error instanceof Error ? error.message : "Unknown cleanup error";

          const failedSummary = {
            run_id: runId,
            started_at: startedAt,
            completed_at: completedAt,
            cutoff_ms: cutoffMs,
            retention_days: RAW_LOG_RETENTION_DAYS,
            deleted: {
              sensor_logs: 0,
              breaker_01: 0,
              breaker_02: 0,
            },
            status: "failed",
            error_message: errorMessage,
          };

          await cleanupRunRef.set(failedSummary);
          await latestCleanupRef.set(failedSummary);

          logger.error("Cleanup failed for home", {
            homeId,
            error: errorMessage,
          });
        }
      }

      logger.info("Raw log cleanup completed.", { cutoffMs, runId });
    } catch (error) {
      logger.error("Error running cleanup scheduler", error);
    }
  }
);
