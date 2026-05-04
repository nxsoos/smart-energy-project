import { onValueCreated } from "firebase-functions/v2/database";
import * as logger from "firebase-functions/logger";
import { admin } from "../firebase";
import {
  DATABASE_INSTANCE,
  DATABASE_REGION,
  ELECTRICITY_TARIFF_BHD_PER_KWH,
  HIGH_POWER_THRESHOLD_W,
} from "../config";
import type { BreakerLog } from "../types";
import {
  createOrUpdateActiveAlert,
  getPrimaryAlertSnapshot,
  markAlertResolving,
  resolveAlertToHistory,
} from "../alerts";
import { resolveRecommendation, upsertRecommendation } from "../recommendations";
import { getBahrainDayId, msToIso, nowTimestamp } from "../utils";

export const analyzeBreakerLog = onValueCreated(
  {
    ref: "/homes/{homeId}/history/{breakerId}/{logId}",
    instance: DATABASE_INSTANCE,
    region: DATABASE_REGION,
  },
  async (event) => {
    try {
      const snapshot = event.data;

      if (!snapshot) {
        logger.info("No breaker snapshot data found.");
        return;
      }

      const log = snapshot.val() as BreakerLog;
      const { homeId, breakerId, logId } = event.params;

      // Ignore non-breaker history paths, such as sensor_logs.
      if (!breakerId.startsWith("breaker_")) {
        return;
      }

      // Ignore records that do not look like breaker/metering logs.
      if (
        typeof log.power_W !== "number" &&
        typeof log.voltage_V !== "number" &&
        typeof log.current_A !== "number"
      ) {
        logger.info("Skipped non-metering breaker log", {
          homeId,
          breakerId,
          logId,
        });
        return;
      }

      const now = Date.now();
      const measurementTimestampMs =
        typeof log.timestamp_ms === "number" ? log.timestamp_ms : now;

      const powerW = typeof log.power_W === "number" ? log.power_W : 0;
      const voltageV = typeof log.voltage_V === "number" ? log.voltage_V : null;
      const currentA = typeof log.current_A === "number" ? log.current_A : null;
      const breakerEnergyKwh =
        typeof log.energy_kWh === "number" ? log.energy_kWh : null;

      const backendRef = admin.database().ref(`/homes/${homeId}/backend`);

      const breakerStateRef = backendRef.child(`energy/branches/${breakerId}`);
      const totalStateRef = backendRef.child("energy/current_total");

      const deviceRef = admin
        .database()
        .ref(`/homes/${homeId}/devices/${breakerId}`);
      const breakerStatusRef = admin
        .database()
        .ref(`/homes/${homeId}/devices/${breakerId}/status`);

      const deviceSnap = await deviceRef.get();
      const device = deviceSnap.exists() ? deviceSnap.val() : {};

      const breakerName = device.name ?? breakerId;
      const breakerType = device.type ?? "smart_breaker";
      const relayStatus = device.status?.relay_status ?? log.relay_status ?? null;
      const switchState = device.status?.switch ?? log.switch ?? null;

      // --------------------------------------------------
      // 1) ESTIMATE ENERGY FROM POWER OVER TIME
      // --------------------------------------------------
      const previousSnap = await breakerStateRef.get();
      const previousState = previousSnap.exists() ? previousSnap.val() : null;

      const previousSeenAt =
        typeof previousState?.last_seen_at === "number"
          ? previousState.last_seen_at
          : null;

      const previousTotalEstimatedKwh =
        typeof previousState?.total_estimated_energy_kWh === "number"
          ? previousState.total_estimated_energy_kWh
          : 0;

      let elapsedMs = 0;
      let estimatedEnergyIncrementKwh = 0;

      if (
        previousSeenAt !== null &&
        measurementTimestampMs > previousSeenAt
      ) {
        elapsedMs = measurementTimestampMs - previousSeenAt;

        // Safety limit:
        // If there is a very large time gap, ignore it to avoid fake huge energy jumps.
        if (elapsedMs <= 10 * 60 * 1000) {
          const elapsedHours = elapsedMs / (1000 * 60 * 60);
          estimatedEnergyIncrementKwh = (powerW * elapsedHours) / 1000;
        }
      }

      const newTotalEstimatedKwh =
        previousTotalEstimatedKwh + estimatedEnergyIncrementKwh;

      const estimatedCostIncrementBHD =
        estimatedEnergyIncrementKwh * ELECTRICITY_TARIFF_BHD_PER_KWH;

      const breakerTotalEstimatedCostBHD =
        newTotalEstimatedKwh * ELECTRICITY_TARIFF_BHD_PER_KWH;

      // --------------------------------------------------
      // 2) UPDATE CURRENT BREAKER ENERGY STATE
      // --------------------------------------------------
      const breakerState = {
        ...nowTimestamp(measurementTimestampMs),
        breaker_id: breakerId,
        name: breakerName,
        type: breakerType,
        last_log_id: logId,
        last_seen_at: measurementTimestampMs,
        last_seen_ms: measurementTimestampMs,
        last_seen_iso: msToIso(measurementTimestampMs),

        voltage_V: voltageV,
        current_A: currentA,
        power_W: powerW,

        breaker_reported_energy_kWh: breakerEnergyKwh,

        estimated_energy_increment_kWh: Number(
          estimatedEnergyIncrementKwh.toFixed(8)
        ),
        total_estimated_energy_kWh: Number(newTotalEstimatedKwh.toFixed(6)),

        estimated_cost_increment_BHD: Number(
          estimatedCostIncrementBHD.toFixed(6)
        ),
        total_estimated_cost_BHD: Number(
          breakerTotalEstimatedCostBHD.toFixed(6)
        ),

        tariff_BHD_per_kWh: ELECTRICITY_TARIFF_BHD_PER_KWH,

        relay_status: relayStatus,
        switch: switchState,
      };

      await breakerStateRef.set(breakerState);

      await breakerStatusRef.update({
        ...nowTimestamp(measurementTimestampMs),
        lastSeenMs: measurementTimestampMs,
        last_seen_ms: measurementTimestampMs,
        last_seen_iso: msToIso(measurementTimestampMs),
      });

      // --------------------------------------------------
      // 3) UPDATE TODAY'S TOTAL FOR THIS BREAKER
      // --------------------------------------------------
      const todayId = getBahrainDayId(measurementTimestampMs);

      const todayRef = backendRef.child(
        `energy/daily_totals/${todayId}/branches/${breakerId}`
      );

      const todaySnap = await todayRef.get();
      const todayData = todaySnap.exists() ? todaySnap.val() : {};

      const todayEnergyKwh =
        (typeof todayData.estimated_energy_kWh === "number"
          ? todayData.estimated_energy_kWh
          : 0) + estimatedEnergyIncrementKwh;

      const todayCostBHD = todayEnergyKwh * ELECTRICITY_TARIFF_BHD_PER_KWH;

      await todayRef.set({
        ...nowTimestamp(now),
        breaker_id: breakerId,
        name: breakerName,

        estimated_energy_kWh: Number(todayEnergyKwh.toFixed(6)),
        estimated_cost_BHD: Number(todayCostBHD.toFixed(6)),

        last_power_W: powerW,
        last_voltage_V: voltageV,
        last_current_A: currentA,
        last_seen_at: now,
        last_seen_ms: now,
        last_seen_iso: msToIso(now),

        tariff_BHD_per_kWh: ELECTRICITY_TARIFF_BHD_PER_KWH,
      });

      // --------------------------------------------------
      // 4) UPDATE TOTAL CURRENT ENERGY STATE FOR ALL BREAKERS
      // --------------------------------------------------
      const branchesSnap = await backendRef.child("energy/branches").get();

      let totalPowerW = 0;
      let totalEstimatedEnergyKwh = 0;
      let totalEstimatedCostBHD = 0;

      const branches: Record<string, unknown> = {};

      if (branchesSnap.exists()) {
        const branchesData = branchesSnap.val();

        for (const id of Object.keys(branchesData)) {
          const branch = branchesData[id];

          totalPowerW +=
            typeof branch.power_W === "number" ? branch.power_W : 0;

          totalEstimatedEnergyKwh +=
            typeof branch.total_estimated_energy_kWh === "number"
              ? branch.total_estimated_energy_kWh
              : 0;

          totalEstimatedCostBHD +=
            typeof branch.total_estimated_cost_BHD === "number"
              ? branch.total_estimated_cost_BHD
              : 0;

          branches[id] = {
            name: branch.name ?? id,
            power_W: branch.power_W ?? 0,
            voltage_V: branch.voltage_V ?? null,
            current_A: branch.current_A ?? null,
            estimated_energy_kWh: branch.total_estimated_energy_kWh ?? 0,
            estimated_cost_BHD: branch.total_estimated_cost_BHD ?? 0,
            switch: branch.switch ?? null,
            relay_status: branch.relay_status ?? null,
            last_seen_at: branch.last_seen_at ?? null,
            last_seen_ms: branch.last_seen_ms ?? branch.last_seen_at ?? null,
            last_seen_iso: branch.last_seen_iso ?? msToIso(branch.last_seen_at),
          };
        }
      }

      await totalStateRef.set({
        ...nowTimestamp(now),
        total_power_W: Number(totalPowerW.toFixed(2)),
        total_estimated_energy_kWh: Number(totalEstimatedEnergyKwh.toFixed(6)),
        total_estimated_cost_BHD: Number(totalEstimatedCostBHD.toFixed(6)),
        tariff_BHD_per_kWh: ELECTRICITY_TARIFF_BHD_PER_KWH,
        updated_at: now,
        updated_at_ms: now,
        updated_at_iso: msToIso(now),
        branches,
      });

      await backendRef.child("dashboard/energy").set({
        ...nowTimestamp(now),
        updated_at: now,
        updated_at_ms: now,
        updated_at_iso: msToIso(now),

        total_power_W: Number(totalPowerW.toFixed(2)),
        total_estimated_energy_kWh: Number(totalEstimatedEnergyKwh.toFixed(6)),
        total_estimated_cost_BHD: Number(totalEstimatedCostBHD.toFixed(6)),
        tariff_BHD_per_kWh: ELECTRICITY_TARIFF_BHD_PER_KWH,

        branches,
      });
      // --------------------------------------------------
      // 5) HIGH POWER ALERT LIFECYCLE
      // --------------------------------------------------
      const highPowerAlertKey = `high_power_usage_${breakerId}`;
      const highPowerRecommendationKey = `energy_saving_${breakerId}`;

      if (powerW >= HIGH_POWER_THRESHOLD_W) {
        const existingHighPowerSnap = await getPrimaryAlertSnapshot(
          backendRef,
          highPowerAlertKey,
          { mirrorToEnergy: true }
        );

        const previousPeakPower =
          existingHighPowerSnap && existingHighPowerSnap.exists()
            ? (() => {
                const existing = existingHighPowerSnap.val() as Record<string, unknown>;
                return typeof existing.peak_power_W === "number"
                  ? existing.peak_power_W
                  : powerW;
              })()
            : powerW;

        await createOrUpdateActiveAlert(
          backendRef,
          highPowerAlertKey,
          {
            type: "electricity",
            subtype: "high_power_usage",
            level: "medium",
            message: `${breakerName} is using high power`,
            source: "breaker_analysis",
            source_log: logId,
            additionalFields: {
              breaker_id: breakerId,
              breaker_name: breakerName,
              threshold_W: HIGH_POWER_THRESHOLD_W,
              latest_power_W: powerW,
              peak_power_W: Math.max(previousPeakPower, powerW),
            },
          },
          now,
          { mirrorToEnergy: true }
        );

        await upsertRecommendation(
          backendRef,
          highPowerRecommendationKey,
          {
            type: "energy_saving",
            priority: "medium",
            title: "High breaker power usage",
            message:
              "Switch Breaker is using more power than expected. Check if unnecessary devices are connected.",
            source: "backend_analysis",
            related_device_id: breakerId,
            related_alert_key: highPowerAlertKey,
          },
          now
        );

        logger.info("Updated high-power alert state", {
          homeId,
          breakerId,
          powerW,
        });
      } else {
        await markAlertResolving(
          backendRef,
          highPowerAlertKey,
          now,
          { mirrorToEnergy: true }
        );

        const resolved = await resolveAlertToHistory(
          backendRef,
          highPowerAlertKey,
          now,
          { mirrorToEnergy: true }
        );

        if (resolved) {
          await resolveRecommendation(
            backendRef,
            highPowerRecommendationKey,
            now
          );
        }
      }


      const activeEnergyAlertsSnap = await backendRef
      .child("energy/active_alerts")
      .get();

      const activeEnergyAlertsCount = activeEnergyAlertsSnap.exists()
      ? Object.keys(activeEnergyAlertsSnap.val()).length
      : 0;

      await backendRef.child("dashboard/alerts").update({
        ...nowTimestamp(now),
        active_energy_alerts_count: activeEnergyAlertsCount,
        updated_at: now,
        updated_at_ms: now,
        updated_at_iso: msToIso(now),
      });

      logger.info("Breaker log processed successfully", {
        homeId,
        breakerId,
        logId,
        powerW,
        estimatedEnergyIncrementKwh,
      });
    } catch (error) {
      logger.error("Error processing breaker log", error);
    }
  }
);
