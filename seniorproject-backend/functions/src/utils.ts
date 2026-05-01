export function roundTo(value: number, decimals: number): number {
  return Number(value.toFixed(decimals));
}

export function isValidPowerW(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function getBahrainHourId(timestampMs: number): string {
  const BAHRAIN_OFFSET_MS = 3 * 60 * 60 * 1000;
  const bahrainDate = new Date(timestampMs + BAHRAIN_OFFSET_MS);

  const year = bahrainDate.getUTCFullYear();
  const month = String(bahrainDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(bahrainDate.getUTCDate()).padStart(2, "0");
  const hour = String(bahrainDate.getUTCHours()).padStart(2, "0");

  return `${year}-${month}-${day}_${hour}`;
}

export function getBahrainDayId(timestampMs: number): string {
  const BAHRAIN_OFFSET_MS = 3 * 60 * 60 * 1000;
  const bahrainDate = new Date(timestampMs + BAHRAIN_OFFSET_MS);

  const year = bahrainDate.getUTCFullYear();
  const month = String(bahrainDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(bahrainDate.getUTCDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}
