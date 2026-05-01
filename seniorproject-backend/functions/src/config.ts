export const DATABASE_INSTANCE = "seniorproject-energy-default-rtdb";
export const DATABASE_REGION = "asia-southeast1";

export const LIGHT_NO_MOTION_DELAY_MS = 5 * 60 * 1000; // 5 minutes
export const HIGH_TEMP_DELAY_MS = 5 * 60 * 1000; // 5 minutes
export const HIGH_TEMP_THRESHOLD = 27;

export const ELECTRICITY_TARIFF_BHD_PER_KWH = 0.032; // 32 fils per kWh
export const HIGH_POWER_THRESHOLD_W = 5;
export const ALERT_COOLDOWN_MS = 60 * 1000; // 1 minute
export const ALERT_RESOLVE_AFTER_MS = 5 * 60 * 1000; // 5 minutes
export const DEVICE_OFFLINE_AFTER_MS = 3 * 60 * 1000; // 3 minutes
export const RAW_LOG_RETENTION_DAYS = 7;
export const ONE_DAY_MS = 24 * 60 * 60 * 1000;
export const ONE_HOUR_MS = 60 * 60 * 1000;

export const BREAKER_IDS = ["breaker_01", "breaker_02"] as const;
export type BreakerId = (typeof BREAKER_IDS)[number];

export const DEFAULT_BREAKER_NAMES: Record<BreakerId, string> = {
  breaker_01: "Switch Breaker",
  breaker_02: "AC Breaker",
};
