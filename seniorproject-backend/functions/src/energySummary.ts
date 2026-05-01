import { admin } from "./firebase";
import {
  BREAKER_IDS,
  DEFAULT_BREAKER_NAMES,
  ELECTRICITY_TARIFF_BHD_PER_KWH,
  ONE_HOUR_MS,
} from "./config";
import type { BreakerId } from "./config";
import type { BreakerLog, HourlyEnergyBranchSummary, HourlyEnergySummary } from "./types";
import { isValidPowerW, roundTo } from "./utils";

export function getBreakerNameFromDevices(
  devicesData: Record<string, any>,
  breakerId: BreakerId
): string {
  const configuredName = devicesData[breakerId]?.name;
  return typeof configuredName === "string"
    ? configuredName
    : DEFAULT_BREAKER_NAMES[breakerId];
}

export function summarizeHourlyBreakerEnergy(
  logsSnap: admin.database.DataSnapshot,
  breakerName: string
): HourlyEnergyBranchSummary {
  const samples: Array<{ timestamp_ms: number; power_W: number }> = [];

  if (logsSnap.exists()) {
    logsSnap.forEach((child) => {
      const log = child.val() as BreakerLog;

      if (!isValidPowerW(log.power_W)) {
        return false;
      }

      const childKeyAsNumber = Number(child.key);
      const timestampMs =
        typeof log.timestamp_ms === "number" && Number.isFinite(log.timestamp_ms)
          ? log.timestamp_ms
          : childKeyAsNumber;

      if (!Number.isFinite(timestampMs)) {
        return false;
      }

      samples.push({
        timestamp_ms: timestampMs,
        power_W: log.power_W,
      });

      return false;
    });
  }

  samples.sort((a, b) => a.timestamp_ms - b.timestamp_ms);

  let sumPowerW = 0;
  let peakPowerW = 0;
  let minPowerW = 0;

  if (samples.length > 0) {
    minPowerW = samples[0].power_W;

    for (const sample of samples) {
      sumPowerW += sample.power_W;
      peakPowerW = Math.max(peakPowerW, sample.power_W);
      minPowerW = Math.min(minPowerW, sample.power_W);
    }
  }

  let estimatedEnergyKwh = 0;

  if (samples.length >= 2) {
    for (let i = 1; i < samples.length; i++) {
      const previous = samples[i - 1];
      const current = samples[i];

      const elapsedMs = current.timestamp_ms - previous.timestamp_ms;

      if (elapsedMs <= 0) {
        continue;
      }

      const elapsedHours = elapsedMs / ONE_HOUR_MS;
      estimatedEnergyKwh += (previous.power_W * elapsedHours) / 1000;
    }
  }

  const averagePowerW = samples.length > 0 ? sumPowerW / samples.length : 0;

  return {
    name: breakerName,
    avg_power_W: roundTo(averagePowerW, 2),
    peak_power_W: roundTo(peakPowerW, 2),
    min_power_W: roundTo(minPowerW, 2),
    sample_count: samples.length,
    estimated_energy_kWh: roundTo(estimatedEnergyKwh, 6),
    estimated_cost_BHD: roundTo(
      estimatedEnergyKwh * ELECTRICITY_TARIFF_BHD_PER_KWH,
      6
    ),
  };
}

export function hasHourlyEnergyData(energySummary: HourlyEnergySummary): boolean {
  return BREAKER_IDS.some(
    (breakerId) => energySummary.branches[breakerId].sample_count > 0
  );
}
