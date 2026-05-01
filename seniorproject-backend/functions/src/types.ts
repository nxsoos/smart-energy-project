import type { BreakerId } from "./config";

export type PendingCondition = {
  active: boolean;
  started_at: number;
  last_seen_at: number;
  alert_sent: boolean;
  type: string;
  source_log?: string;
};

export type BreakerLog = {
  voltage_V?: number;
  current_A?: number;
  current_mA?: number;
  power_W?: number;
  energy_kWh?: number;
  relay_status?: string;
  switch?: boolean;
  timestamp_ms?: number;
  readable_time?: string;
};

export type RecommendationType =
  | "energy_saving"
  | "comfort"
  | "safety"
  | "device_health"
  | "usage_pattern";

export type RecommendationPriority = "low" | "medium" | "high";

export type RecommendationStatus = "active" | "dismissed" | "resolved";

export type RecommendationRecord = {
  recommendation_id: string;
  type: RecommendationType;
  priority: RecommendationPriority;
  title: string;
  message: string;
  source: string;
  related_device_id: string | null;
  related_alert_key: string | null;
  status: RecommendationStatus;
  created_at: number;
  resolved_at: number | null;
  updated_at?: number;
};

export type UpsertRecommendationInput = {
  type: RecommendationType;
  priority: RecommendationPriority;
  title: string;
  message: string;
  source: string;
  related_device_id?: string | null;
  related_alert_key?: string | null;
};

export type HourlyEnergyBranchSummary = {
  name: string;
  avg_power_W: number;
  peak_power_W: number;
  min_power_W: number;
  sample_count: number;
  estimated_energy_kWh: number;
  estimated_cost_BHD: number;
};

export type HourlyEnergySummary = {
  total_avg_power_W: number;
  total_peak_power_W: number;
  total_estimated_energy_kWh: number;
  total_estimated_cost_BHD: number;
  tariff_BHD_per_kWh: number;
  branches: Record<BreakerId, HourlyEnergyBranchSummary>;
};

export type DailyEnergyBranchSummary = {
  name: string;
  total_energy_kWh: number;
  total_cost_BHD: number;
  avg_power_W: number;
  peak_power_W: number;
  active_hours: number;
};

export type DailyEnergySummary = {
  total_energy_kWh: number;
  total_cost_BHD: number;
  avg_power_W: number;
  peak_power_W: number;
  tariff_BHD_per_kWh: number;
  highest_consuming_breaker: BreakerId | null;
  branches: Record<BreakerId, DailyEnergyBranchSummary>;
};

export type AlertStatus = "active" | "resolving" | "resolved";
export type AlertLevel = "low" | "medium" | "high" | "critical";

export type ActiveAlertRecord = {
  alert_key: string;
  type: string;
  subtype: string;
  level: AlertLevel;
  status: AlertStatus;
  message: string;
  first_detected_at: number;
  last_seen_at: number;
  last_triggered_at: number;
  last_seen_normal_at: number | null;
  alert_count: number;
  source: string;
  source_log: string | null;
  [key: string]: unknown;
};

export type AlertLifecycleOptions = {
  mirrorToEnergy: boolean;
};

export type AlertCreateInput = {
  type: string;
  subtype: string;
  level: AlertLevel;
  message: string;
  source: string;
  source_log?: string | null;
  additionalFields?: Record<string, unknown>;
};

export type DeviceHealthStatus = "online" | "offline" | "unknown";
