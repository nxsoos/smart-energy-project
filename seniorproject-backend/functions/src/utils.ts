export function roundTo(value: number, decimals: number): number {
  return Number(value.toFixed(decimals));
}

export const TIMEZONE = "Asia/Bahrain";
export const BAHRAIN_OFFSET_MS = 3 * 60 * 60 * 1000;

function bahrainDateParts(timestampMs: number): {
  year: number;
  month: string;
  day: string;
  hour: string;
  minute: string;
  second: string;
} {
  const bahrainDate = new Date(timestampMs + BAHRAIN_OFFSET_MS);
  return {
    year: bahrainDate.getUTCFullYear(),
    month: String(bahrainDate.getUTCMonth() + 1).padStart(2, "0"),
    day: String(bahrainDate.getUTCDate()).padStart(2, "0"),
    hour: String(bahrainDate.getUTCHours()).padStart(2, "0"),
    minute: String(bahrainDate.getUTCMinutes()).padStart(2, "0"),
    second: String(bahrainDate.getUTCSeconds()).padStart(2, "0"),
  };
}

export function nowMs(): number {
  return Date.now();
}

export function msToIso(timestampMs: unknown): string | null {
  if (typeof timestampMs !== "number" || !Number.isFinite(timestampMs) || timestampMs <= 0) {
    return null;
  }
  const parts = bahrainDateParts(timestampMs);
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}+03:00`;
}

export function nowIso(): string {
  return msToIso(nowMs()) ?? "";
}

export function nowTimestamp(timestampMs = nowMs()): {
  timestamp_ms: number;
  timestamp_iso: string | null;
  timezone: string;
} {
  return {
    timestamp_ms: timestampMs,
    timestamp_iso: msToIso(timestampMs),
    timezone: TIMEZONE,
  };
}

export function isoToMs(timestampIso: unknown): number | null {
  if (typeof timestampIso !== "string" || timestampIso.trim() === "") {
    return null;
  }
  const parsed = Date.parse(timestampIso);
  return Number.isFinite(parsed) ? parsed : null;
}

export function isValidPowerW(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function getBahrainHourId(timestampMs: number): string {
  const bahrainDate = new Date(timestampMs + BAHRAIN_OFFSET_MS);

  const year = bahrainDate.getUTCFullYear();
  const month = String(bahrainDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(bahrainDate.getUTCDate()).padStart(2, "0");
  const hour = String(bahrainDate.getUTCHours()).padStart(2, "0");

  return `${year}-${month}-${day}_${hour}`;
}

export function getBahrainDayId(timestampMs: number): string {
  const bahrainDate = new Date(timestampMs + BAHRAIN_OFFSET_MS);

  const year = bahrainDate.getUTCFullYear();
  const month = String(bahrainDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(bahrainDate.getUTCDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}
