import { admin } from "./firebase";
import { ALERT_COOLDOWN_MS, ALERT_RESOLVE_AFTER_MS } from "./config";
import type { ActiveAlertRecord, AlertCreateInput, AlertLifecycleOptions } from "./types";

const DEFAULT_ALERT_OPTIONS: AlertLifecycleOptions = {
  mirrorToEnergy: false,
};

function getAlertScopeRefs(
  backendRef: admin.database.Reference,
  alertKey: string,
  options?: Partial<AlertLifecycleOptions>
): Array<{ activeRef: admin.database.Reference; historyRef: admin.database.Reference }> {
  const mergedOptions: AlertLifecycleOptions = {
    ...DEFAULT_ALERT_OPTIONS,
    ...options,
  };

  const refs: Array<{ activeRef: admin.database.Reference; historyRef: admin.database.Reference }> = [
    {
      activeRef: backendRef.child(`active_alerts/${alertKey}`),
      historyRef: backendRef.child("alert_history"),
    },
  ];

  if (mergedOptions.mirrorToEnergy) {
    refs.push({
      activeRef: backendRef.child(`energy/active_alerts/${alertKey}`),
      historyRef: backendRef.child("energy/alert_history"),
    });
  }

  return refs;
}

export async function getPrimaryAlertSnapshot(
  backendRef: admin.database.Reference,
  alertKey: string,
  options?: Partial<AlertLifecycleOptions>
): Promise<admin.database.DataSnapshot | null> {
  const refs = getAlertScopeRefs(backendRef, alertKey, options);

  for (const ref of refs) {
    const snap = await ref.activeRef.get();
    if (snap.exists()) {
      return snap;
    }
  }

  return null;
}

export async function createOrUpdateActiveAlert(
  backendRef: admin.database.Reference,
  alertKey: string,
  input: AlertCreateInput,
  timestampMs: number,
  options?: Partial<AlertLifecycleOptions>
): Promise<ActiveAlertRecord> {
  const existingSnap = await getPrimaryAlertSnapshot(backendRef, alertKey, options);
  const existing = existingSnap?.exists()
    ? (existingSnap.val() as Partial<ActiveAlertRecord>)
    : null;

  const previousTriggeredAt =
    typeof existing?.last_triggered_at === "number"
      ? existing.last_triggered_at
      : 0;

  const cooldownPassed = timestampMs - previousTriggeredAt >= ALERT_COOLDOWN_MS;

  const alertCount =
    typeof existing?.alert_count === "number"
      ? existing.alert_count + (cooldownPassed ? 1 : 0)
      : 1;

  const nextAlert: ActiveAlertRecord = {
    ...(existing ?? {}),
    ...(input.additionalFields ?? {}),
    alert_key: alertKey,
    type: input.type,
    subtype: input.subtype,
    level: input.level,
    status: "active",
    message: input.message,
    first_detected_at:
      typeof existing?.first_detected_at === "number"
        ? existing.first_detected_at
        : timestampMs,
    last_seen_at: timestampMs,
    last_triggered_at: cooldownPassed
      ? timestampMs
      : typeof existing?.last_triggered_at === "number"
      ? existing.last_triggered_at
      : timestampMs,
    last_seen_normal_at: null,
    alert_count: alertCount,
    source: input.source,
    source_log: input.source_log ?? null,
  };

  const refs = getAlertScopeRefs(backendRef, alertKey, options);
  await Promise.all(refs.map((ref) => ref.activeRef.set(nextAlert)));

  return nextAlert;
}

export async function markAlertResolving(
  backendRef: admin.database.Reference,
  alertKey: string,
  timestampMs: number,
  options?: Partial<AlertLifecycleOptions>
): Promise<void> {
  const refs = getAlertScopeRefs(backendRef, alertKey, options);

  await Promise.all(
    refs.map(async (ref) => {
      const alertSnap = await ref.activeRef.get();

      if (!alertSnap.exists()) {
        return;
      }

      const alert = alertSnap.val() as Partial<ActiveAlertRecord>;
      const lastSeenNormalAt =
        typeof alert.last_seen_normal_at === "number"
          ? alert.last_seen_normal_at
          : timestampMs;

      await ref.activeRef.update({
        status: "resolving",
        last_seen_at: timestampMs,
        last_seen_normal_at: lastSeenNormalAt,
      });
    })
  );
}

export async function resolveAlertToHistory(
  backendRef: admin.database.Reference,
  alertKey: string,
  timestampMs: number,
  options?: Partial<AlertLifecycleOptions>
): Promise<boolean> {
  const refs = getAlertScopeRefs(backendRef, alertKey, options);
  let resolved = false;

  await Promise.all(
    refs.map(async (ref) => {
      const alertSnap = await ref.activeRef.get();

      if (!alertSnap.exists()) {
        return;
      }

      const alert = alertSnap.val() as Partial<ActiveAlertRecord>;

      const normalSince =
        typeof alert.last_seen_normal_at === "number"
          ? alert.last_seen_normal_at
          : null;

      if (normalSince === null || timestampMs - normalSince < ALERT_RESOLVE_AFTER_MS) {
        return;
      }

      const firstDetectedAt =
        typeof alert.first_detected_at === "number"
          ? alert.first_detected_at
          : timestampMs;

      const historyKey = `${alertKey}_${firstDetectedAt}`;

      await ref.historyRef.child(historyKey).set({
        ...alert,
        status: "resolved",
        resolved_at: timestampMs,
        duration_ms: timestampMs - firstDetectedAt,
      });

      await ref.activeRef.remove();
      resolved = true;
    })
  );

  return resolved;
}

export async function setAlertActiveOrResolve(
  backendRef: admin.database.Reference,
  params: {
    alertKey: string;
    isActive: boolean;
    createInput?: AlertCreateInput;
    timestampMs: number;
    options?: Partial<AlertLifecycleOptions>;
  }
): Promise<void> {
  if (params.isActive && params.createInput) {
    await createOrUpdateActiveAlert(
      backendRef,
      params.alertKey,
      params.createInput,
      params.timestampMs,
      params.options
    );
    return;
  }

  await markAlertResolving(
    backendRef,
    params.alertKey,
    params.timestampMs,
    params.options
  );

  await resolveAlertToHistory(
    backendRef,
    params.alertKey,
    params.timestampMs,
    params.options
  );
}
