import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";
import { admin } from "../firebase";
import {
  BREAKER_IDS,
  DATABASE_REGION,
  ELECTRICITY_TARIFF_BHD_PER_KWH,
  HIGH_TEMP_THRESHOLD,
  ONE_HOUR_MS,
} from "../config";
import type { BreakerId } from "../config";
import type { DailyEnergyBranchSummary, DailyEnergySummary, HourlyEnergySummary } from "../types";
import {
  getBreakerNameFromDevices,
  hasHourlyEnergyData,
  summarizeHourlyBreakerEnergy,
} from "../energySummary";
import {
  BAHRAIN_OFFSET_MS,
  getBahrainDayId,
  getBahrainHourId,
  msToIso,
  nowTimestamp,
  roundTo,
} from "../utils";

export const generateHourlySummaries = onSchedule(
  {
    schedule: "5 * * * *", // every hour at minute 5
    region: DATABASE_REGION,
    timeZone: "Asia/Bahrain",
  },
  async () => {
    try {
      const now = Date.now();

      // Previous completed Bahrain hour
      const currentBahrainHourStart =
        Math.floor((now + BAHRAIN_OFFSET_MS) / ONE_HOUR_MS) * ONE_HOUR_MS -
        BAHRAIN_OFFSET_MS;

      const hourStart = currentBahrainHourStart - ONE_HOUR_MS;
      const hourEnd = currentBahrainHourStart - 1;

      const hourId = getBahrainHourId(hourStart);

      const homesRef = admin.database().ref("/homes");
      const homesSnap = await homesRef.get();

      if (!homesSnap.exists()) {
        logger.info("No homes found for hourly summary.");
        return;
      }

      const homes = homesSnap.val();

      for (const homeId of Object.keys(homes)) {
        const sensorLogsRef = admin.database().ref(`/homes/${homeId}/history/sensor_logs`);
        const breaker1LogsRef = admin.database().ref(`/homes/${homeId}/history/breaker_01`);
        const breaker2LogsRef = admin.database().ref(`/homes/${homeId}/history/breaker_02`);
        const devicesRef = admin.database().ref(`/homes/${homeId}/devices`);

        const [sensorLogsSnap, breaker1LogsSnap, breaker2LogsSnap, devicesSnap] =
          await Promise.all([
            sensorLogsRef
              .orderByChild("timestamp_ms")
              .startAt(hourStart)
              .endAt(hourEnd)
              .get(),
            breaker1LogsRef
              .orderByChild("timestamp_ms")
              .startAt(hourStart)
              .endAt(hourEnd)
              .get(),
            breaker2LogsRef
              .orderByChild("timestamp_ms")
              .startAt(hourStart)
              .endAt(hourEnd)
              .get(),
            devicesRef.get(),
          ]);

        const devicesData = devicesSnap.exists()
          ? (devicesSnap.val() as Record<string, any>)
          : {};

        const breaker1Summary = summarizeHourlyBreakerEnergy(
          breaker1LogsSnap,
          getBreakerNameFromDevices(devicesData, "breaker_01")
        );
        const breaker2Summary = summarizeHourlyBreakerEnergy(
          breaker2LogsSnap,
          getBreakerNameFromDevices(devicesData, "breaker_02")
        );

        const hourlyEnergy: HourlyEnergySummary = {
          total_avg_power_W: roundTo(
            breaker1Summary.avg_power_W + breaker2Summary.avg_power_W,
            2
          ),
          total_peak_power_W: roundTo(
            Math.max(breaker1Summary.peak_power_W, breaker2Summary.peak_power_W),
            2
          ),
          total_estimated_energy_kWh: roundTo(
            breaker1Summary.estimated_energy_kWh +
              breaker2Summary.estimated_energy_kWh,
            6
          ),
          total_estimated_cost_BHD: roundTo(
            breaker1Summary.estimated_cost_BHD + breaker2Summary.estimated_cost_BHD,
            6
          ),
          tariff_BHD_per_kWh: ELECTRICITY_TARIFF_BHD_PER_KWH,
          branches: {
            breaker_01: breaker1Summary,
            breaker_02: breaker2Summary,
          },
        };

        let sampleCount = 0;

        let temperatureSum = 0;
        let temperatureCount = 0;

        let humiditySum = 0;
        let humidityCount = 0;

        let soundRawSum = 0;
        let soundRawCount = 0;

        let motionCount = 0;
        let brightCount = 0;
        let smokeCount = 0;
        let noiseCount = 0;
        let highTempCount = 0;

        if (sensorLogsSnap.exists()) {
          sensorLogsSnap.forEach((child) => {
            const log = child.val();
            sampleCount++;

            if (typeof log.temperature === "number" && log.temperature >= 0) {
              temperatureSum += log.temperature;
              temperatureCount++;
            }

            if (typeof log.humidity === "number" && log.humidity >= 0) {
              humiditySum += log.humidity;
              humidityCount++;
            }

            if (typeof log.sound_raw === "number" && log.sound_raw >= 0) {
              soundRawSum += log.sound_raw;
              soundRawCount++;
            }

            if (log.motion === 1) {
              motionCount++;
            }

            if (log.light_status === "Bright") {
              brightCount++;
            }

            if (log.smoke === 1) {
              smokeCount++;
            }

            if (log.noise === 1) {
              noiseCount++;
            }

            if (
              typeof log.temperature === "number" &&
              log.temperature >= HIGH_TEMP_THRESHOLD
            ) {
              highTempCount++;
            }

            return false;
          });
        }

        const avgTemperature =
          temperatureCount > 0
            ? Number((temperatureSum / temperatureCount).toFixed(2))
            : null;

        const avgHumidity =
          humidityCount > 0
            ? Number((humiditySum / humidityCount).toFixed(2))
            : null;

        const avgSoundRaw =
          soundRawCount > 0
            ? Number((soundRawSum / soundRawCount).toFixed(2))
            : null;

        const status =
          sampleCount > 0 || hasHourlyEnergyData(hourlyEnergy)
            ? "completed"
            : "no_data";

        const summary = {
          ...nowTimestamp(now),
          hour_id: hourId,
          hour_start: hourStart,
          hour_start_ms: hourStart,
          hour_start_iso: msToIso(hourStart),
          hour_end: hourEnd,
          hour_end_ms: hourEnd,
          hour_end_iso: msToIso(hourEnd),
          sample_count: sampleCount,
          avg_temperature: avgTemperature,
          avg_humidity: avgHumidity,
          avg_sound_raw: avgSoundRaw,
          motion_count: motionCount,
          bright_count: brightCount,
          smoke_count: smokeCount,
          noise_count: noiseCount,
          high_temp_count: highTempCount,
          energy: hourlyEnergy,
          created_at: now,
          created_at_ms: now,
          created_at_iso: msToIso(now),
          status,
        };

        await admin
          .database()
          .ref(`/homes/${homeId}/history/hourly_summaries/${hourId}`)
          .set(summary);

        await admin
          .database()
          .ref(`/homes/${homeId}/backend/latest_hourly_summary`)
          .set(summary);

        logger.info("Hourly summary created successfully.", {
          homeId,
          hourId,
          sampleCount,
          energySampleCount:
            breaker1Summary.sample_count + breaker2Summary.sample_count,
          status,
        });
      }
    } catch (error) {
      logger.error("Error generating hourly summaries", error);
    }
  }
);

export const generateDailySummaries = onSchedule(
  {
    schedule: "10 0 * * *", // every day at 00:10 Bahrain time
    region: DATABASE_REGION,
    timeZone: "Asia/Bahrain",
  },
  async () => {
    try {
      const now = Date.now();

      const ONE_DAY_MS = 24 * 60 * 60 * 1000;

      // Get previous completed Bahrain day
      const currentBahrainDayStart =
        Math.floor((now + BAHRAIN_OFFSET_MS) / ONE_DAY_MS) * ONE_DAY_MS -
        BAHRAIN_OFFSET_MS;

      const dayStart = currentBahrainDayStart - ONE_DAY_MS;
      const dayEnd = currentBahrainDayStart - 1;

      const dayId = getBahrainDayId(dayStart);

      const homesRef = admin.database().ref("/homes");
      const homesSnap = await homesRef.get();

      if (!homesSnap.exists()) {
        logger.info("No homes found for daily summary.");
        return;
      }

      const homes = homesSnap.val();

      for (const homeId of Object.keys(homes)) {
        const hourlySummariesRef = admin
          .database()
          .ref(`/homes/${homeId}/history/hourly_summaries`);

        const devicesRef = admin.database().ref(`/homes/${homeId}/devices`);

        const [hourlySnap, devicesSnap] = await Promise.all([
          hourlySummariesRef
            .orderByChild("hour_start")
            .startAt(dayStart)
            .endAt(dayEnd)
            .get(),
          devicesRef.get(),
        ]);

        const devicesData = devicesSnap.exists()
          ? (devicesSnap.val() as Record<string, any>)
          : {};

        const dailyBranchTotals: Record<BreakerId, DailyEnergyBranchSummary> = {
          breaker_01: {
            name: getBreakerNameFromDevices(devicesData, "breaker_01"),
            total_energy_kWh: 0,
            total_cost_BHD: 0,
            avg_power_W: 0,
            peak_power_W: 0,
            active_hours: 0,
          },
          breaker_02: {
            name: getBreakerNameFromDevices(devicesData, "breaker_02"),
            total_energy_kWh: 0,
            total_cost_BHD: 0,
            avg_power_W: 0,
            peak_power_W: 0,
            active_hours: 0,
          },
        };

        let hourCount = 0;
        let sampleCount = 0;

        let weightedTempSum = 0;
        let weightedTempCount = 0;

        let weightedHumiditySum = 0;
        let weightedHumidityCount = 0;

        let weightedSoundRawSum = 0;
        let weightedSoundRawCount = 0;

        let motionCount = 0;
        let brightCount = 0;
        let smokeCount = 0;
        let noiseCount = 0;
        let highTempCount = 0;

        let totalEnergyKwh = 0;
        let totalCostBhd = 0;
        let totalAvgPowerSum = 0;
        let peakPowerW = 0;

        const branchAvgPowerSums: Record<BreakerId, number> = {
          breaker_01: 0,
          breaker_02: 0,
        };

        if (hourlySnap.exists()) {
          hourlySnap.forEach((child) => {
            const summary = child.val() as Record<string, any>;

            if (summary.status !== "completed") {
              return false;
            }

            const hourSamples =
              typeof summary.sample_count === "number"
                ? summary.sample_count
                : 0;

            hourCount++;
            sampleCount += hourSamples;

            if (
              typeof summary.avg_temperature === "number" &&
              hourSamples > 0
            ) {
              weightedTempSum += summary.avg_temperature * hourSamples;
              weightedTempCount += hourSamples;
            }

            if (typeof summary.avg_humidity === "number" && hourSamples > 0) {
              weightedHumiditySum += summary.avg_humidity * hourSamples;
              weightedHumidityCount += hourSamples;
            }

            if (typeof summary.avg_sound_raw === "number" && hourSamples > 0) {
              weightedSoundRawSum += summary.avg_sound_raw * hourSamples;
              weightedSoundRawCount += hourSamples;
            }

            if (typeof summary.motion_count === "number") {
              motionCount += summary.motion_count;
            }

            if (typeof summary.bright_count === "number") {
              brightCount += summary.bright_count;
            }

            if (typeof summary.smoke_count === "number") {
              smokeCount += summary.smoke_count;
            }

            if (typeof summary.noise_count === "number") {
              noiseCount += summary.noise_count;
            }

            if (typeof summary.high_temp_count === "number") {
              highTempCount += summary.high_temp_count;
            }

            const hourlyEnergy =
              typeof summary.energy === "object" && summary.energy !== null
                ? (summary.energy as Record<string, any>)
                : {};

            const hourlyTotalEnergy =
              typeof hourlyEnergy.total_estimated_energy_kWh === "number"
                ? hourlyEnergy.total_estimated_energy_kWh
                : 0;

            const hourlyTotalCost =
              typeof hourlyEnergy.total_estimated_cost_BHD === "number"
                ? hourlyEnergy.total_estimated_cost_BHD
                : 0;

            const hourlyAvgPower =
              typeof hourlyEnergy.total_avg_power_W === "number"
                ? hourlyEnergy.total_avg_power_W
                : 0;

            const hourlyPeakPower =
              typeof hourlyEnergy.total_peak_power_W === "number"
                ? hourlyEnergy.total_peak_power_W
                : 0;

            totalEnergyKwh += hourlyTotalEnergy;
            totalCostBhd += hourlyTotalCost;
            totalAvgPowerSum += hourlyAvgPower;
            peakPowerW = Math.max(peakPowerW, hourlyPeakPower);

            const hourlyBranches =
              typeof hourlyEnergy.branches === "object" &&
              hourlyEnergy.branches !== null
                ? (hourlyEnergy.branches as Record<string, any>)
                : {};

            for (const breakerId of BREAKER_IDS) {
              const hourlyBranch =
                typeof hourlyBranches[breakerId] === "object" &&
                hourlyBranches[breakerId] !== null
                  ? (hourlyBranches[breakerId] as Record<string, any>)
                  : {};

              const branchEnergy =
                typeof hourlyBranch.estimated_energy_kWh === "number"
                  ? hourlyBranch.estimated_energy_kWh
                  : 0;

              const branchCost =
                typeof hourlyBranch.estimated_cost_BHD === "number"
                  ? hourlyBranch.estimated_cost_BHD
                  : 0;

              const branchAvgPower =
                typeof hourlyBranch.avg_power_W === "number"
                  ? hourlyBranch.avg_power_W
                  : 0;

              const branchPeakPower =
                typeof hourlyBranch.peak_power_W === "number"
                  ? hourlyBranch.peak_power_W
                  : 0;

              const branchName =
                typeof hourlyBranch.name === "string"
                  ? hourlyBranch.name
                  : dailyBranchTotals[breakerId].name;

              dailyBranchTotals[breakerId].name = branchName;
              dailyBranchTotals[breakerId].total_energy_kWh += branchEnergy;
              dailyBranchTotals[breakerId].total_cost_BHD += branchCost;
              dailyBranchTotals[breakerId].peak_power_W = Math.max(
                dailyBranchTotals[breakerId].peak_power_W,
                branchPeakPower
              );

              branchAvgPowerSums[breakerId] += branchAvgPower;

              if (branchAvgPower > 0) {
                dailyBranchTotals[breakerId].active_hours++;
              }
            }

            return false;
          });
        }

        const avgTemperature =
          weightedTempCount > 0
            ? Number((weightedTempSum / weightedTempCount).toFixed(2))
            : null;

        const avgHumidity =
          weightedHumidityCount > 0
            ? Number((weightedHumiditySum / weightedHumidityCount).toFixed(2))
            : null;

        const avgSoundRaw =
          weightedSoundRawCount > 0
            ? Number((weightedSoundRawSum / weightedSoundRawCount).toFixed(2))
            : null;

        for (const breakerId of BREAKER_IDS) {
          dailyBranchTotals[breakerId].total_energy_kWh = roundTo(
            dailyBranchTotals[breakerId].total_energy_kWh,
            6
          );
          dailyBranchTotals[breakerId].total_cost_BHD = roundTo(
            dailyBranchTotals[breakerId].total_cost_BHD,
            6
          );
          dailyBranchTotals[breakerId].peak_power_W = roundTo(
            dailyBranchTotals[breakerId].peak_power_W,
            2
          );
          dailyBranchTotals[breakerId].avg_power_W =
            hourCount > 0 ? roundTo(branchAvgPowerSums[breakerId] / hourCount, 2) : 0;
        }

        let highestConsumingBreaker: BreakerId | null = null;
        let highestEnergyKwh = 0;

        for (const breakerId of BREAKER_IDS) {
          const breakerEnergy = dailyBranchTotals[breakerId].total_energy_kWh;

          if (breakerEnergy > highestEnergyKwh) {
            highestEnergyKwh = breakerEnergy;
            highestConsumingBreaker = breakerId;
          }
        }

        const dailyEnergy: DailyEnergySummary = {
          total_energy_kWh: roundTo(totalEnergyKwh, 6),
          total_cost_BHD: roundTo(totalCostBhd, 6),
          avg_power_W: hourCount > 0 ? roundTo(totalAvgPowerSum / hourCount, 2) : 0,
          peak_power_W: roundTo(peakPowerW, 2),
          tariff_BHD_per_kWh: ELECTRICITY_TARIFF_BHD_PER_KWH,
          highest_consuming_breaker: highestConsumingBreaker,
          branches: dailyBranchTotals,
        };

        const dailySummary = {
          ...nowTimestamp(now),
          day_id: dayId,
          day_start: dayStart,
          day_start_ms: dayStart,
          day_start_iso: msToIso(dayStart),
          day_end: dayEnd,
          day_end_ms: dayEnd,
          day_end_iso: msToIso(dayEnd),
          hour_count: hourCount,
          sample_count: sampleCount,
          avg_temperature: avgTemperature,
          avg_humidity: avgHumidity,
          avg_sound_raw: avgSoundRaw,
          motion_count: motionCount,
          bright_count: brightCount,
          smoke_count: smokeCount,
          noise_count: noiseCount,
          high_temp_count: highTempCount,
          energy: dailyEnergy,
          created_at: now,
          created_at_ms: now,
          created_at_iso: msToIso(now),
          status: hourCount > 0 ? "completed" : "no_data",
        };

        await admin
          .database()
          .ref(`/homes/${homeId}/history/daily_summaries/${dayId}`)
          .set(dailySummary);

        await admin
          .database()
          .ref(`/homes/${homeId}/backend/latest_daily_summary`)
          .set(dailySummary);

        logger.info("Daily summary created successfully.", {
          homeId,
          dayId,
          hourCount,
          sampleCount,
        });
      }
    } catch (error) {
      logger.error("Error generating daily summaries", error);
    }
  }
);
