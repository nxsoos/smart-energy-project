import { admin } from "./firebase";
import { msToIso, nowTimestamp } from "./utils";

export type ControlMode = "manual" | "assist" | "auto";
export type SuggestedAction = {
  deviceId: string;
  deviceName: string;
  command: "turn_on" | "turn_off";
  reason: string;
  source: string;
};

const VALID_MODES = new Set(["manual", "assist", "auto"]);

const DEFAULT_AUTOMATION: Record<string, Record<string, unknown>> = {
  breaker_01: {
    manual_allowed: true,
    assist_allowed: true,
    auto_allowed: true,
    auto_actions: ["turn_off"],
    requires_confirmation: false,
    cooldown_ms: 5 * 60 * 1000,
  },
  breaker_02: {
    manual_allowed: true,
    assist_allowed: true,
    auto_allowed: true,
    auto_actions: ["turn_on", "turn_off"],
    requires_confirmation: false,
    comfort_min_temp: 22,
    comfort_max_temp: 25,
    cooldown_ms: 10 * 60 * 1000,
  },
};

const SAFE_AUTO_ACTIONS: Record<string, Set<string>> = {
  breaker_01: new Set(["turn_off"]),
  breaker_02: new Set(["turn_on", "turn_off"]),
};

function targetState(command: string): string {
  return command === "turn_on" ? "on" : "off";
}

function asRecord(value: unknown): Record<string, any> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, any>)
    : {};
}

function normalizeBool(value: unknown): boolean | null {
  if (typeof value === "boolean") {
    return value;
  }
  if (typeof value === "number") {
    return value !== 0;
  }
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (["true", "1", "on", "yes"].includes(text)) {
      return true;
    }
    if (["false", "0", "off", "no"].includes(text)) {
      return false;
    }
  }
  return null;
}

export async function getControlMode(homeId: string): Promise<ControlMode> {
  const ref = admin.database().ref(`/homes/${homeId}/control`);
  const snap = await ref.get();
  const value = asRecord(snap.val());
  const mode = typeof value.mode === "string" ? value.mode.toLowerCase() : "";

  if (VALID_MODES.has(mode)) {
    return mode as ControlMode;
  }

  const now = Date.now();
  await ref.set({
    ...nowTimestamp(now),
    mode: "assist",
    updated_by: "system_default",
    updated_at_ms: now,
    updated_at_iso: msToIso(now),
  });
  return "assist";
}

async function ensureAutomation(
  homeId: string,
  deviceId: string
): Promise<Record<string, any>> {
  const ref = admin.database().ref(`/homes/${homeId}/devices/${deviceId}/automation`);
  const snap = await ref.get();
  const current = asRecord(snap.val());
  if (Object.keys(current).length > 0) {
    return current;
  }

  const fallback = DEFAULT_AUTOMATION[deviceId] ?? {
    manual_allowed: true,
    assist_allowed: false,
    auto_allowed: false,
    auto_actions: [],
    requires_confirmation: true,
  };
  await ref.set(fallback);
  return fallback;
}

export async function createActionSuggestion(
  homeId: string,
  action: SuggestedAction
): Promise<string> {
  const now = Date.now();
  const activeRef = admin.database().ref(`/homes/${homeId}/action_suggestions/active`);
  const activeSnap = await activeRef.get();
  const active = asRecord(activeSnap.val());
  for (const [id, raw] of Object.entries(active)) {
    const suggestion = asRecord(raw);
    if (
      suggestion.device_id === action.deviceId &&
      suggestion.suggested_command === action.command &&
      suggestion.status === "waiting_for_user"
    ) {
      return id;
    }
  }

  const suggestionId = `sug_${now}`;
  await activeRef.child(suggestionId).set({
      ...nowTimestamp(now),
      suggestion_id: suggestionId,
      home_id: homeId,
      device_id: action.deviceId,
      device_name: action.deviceName,
      suggested_command: action.command,
      target_state: targetState(action.command),
      reason: action.reason,
      source: action.source,
      status: "waiting_for_user",
      created_at_ms: now,
      created_at_iso: msToIso(now),
      actions: ["approve", "dismiss"],
    });
  return suggestionId;
}

export async function tryCreateAutomaticCommand(
  homeId: string,
  action: SuggestedAction
): Promise<boolean> {
  const settings = asRecord(
    (await admin.database().ref(`/homes/${homeId}/settings`).get()).val()
  );
  if (settings.auto_control_enabled === false) {
    return false;
  }

  const deviceRef = admin.database().ref(`/homes/${homeId}/devices/${action.deviceId}`);
  const device = asRecord((await deviceRef.get()).val());
  const automation = await ensureAutomation(homeId, action.deviceId);
  const autoActions = Array.isArray(automation.auto_actions)
    ? automation.auto_actions
    : [];

  if (normalizeBool(automation.auto_allowed) !== true) {
    return false;
  }
  if (!autoActions.includes(action.command)) {
    return false;
  }
  if (!SAFE_AUTO_ACTIONS[action.deviceId]?.has(action.command)) {
    return false;
  }
  if (normalizeBool(automation.requires_confirmation) === true) {
    return false;
  }
  if (normalizeBool(device.command_in_progress) === true) {
    return false;
  }

  const emergencyMode = asRecord(
    (await admin.database().ref(`/homes/${homeId}/safety/emergency_mode`).get()).val()
  );
  if (normalizeBool(emergencyMode.active) === true) {
    return false;
  }

  const status = asRecord(device.status);
  const online = normalizeBool(status.online);
  if (online === false) {
    return false;
  }

  const smokeState = asRecord(
    (await admin.database().ref(`/homes/${homeId}/backend/current_state`).get()).val()
  ).smoke;
  const esp32 = asRecord(
    (await admin.database().ref(`/homes/${homeId}/devices/esp32_01/sensors`).get()).val()
  );
  if (normalizeBool(smokeState) === true || normalizeBool(esp32.smoke) === true) {
    return false;
  }

  const state = asRecord(
    (await admin.database().ref(`/homes/${homeId}/automation_state/${action.deviceId}`).get()).val()
  );
  if (typeof state.cooldown_until_ms === "number" && Date.now() < state.cooldown_until_ms) {
    return false;
  }

  const now = Date.now();
  const commandId = `cmd_${now}`;
  const commandRecord = {
    ...nowTimestamp(now),
    command_id: commandId,
    home_id: homeId,
    device_id: action.deviceId,
    device_name: action.deviceName,
    command: action.command,
    action: action.command,
    target_state: targetState(action.command),
    previous_state: normalizeBool(status.switch) === true ? "on" : "off",
    requested_by: "backend_automation",
    reason: action.reason,
    status: "pending",
    requested_at_ms: now,
    requested_at_iso: msToIso(now),
    sent_at_ms: null,
    sent_at_iso: null,
    confirmed_at_ms: null,
    confirmed_at_iso: null,
    failed_at_ms: null,
    failed_at_iso: null,
    timeout_at_ms: null,
    timeout_at_iso: null,
    result: {
      success: null,
      actual_state: null,
      error_code: null,
      user_message: null,
      raw_error: null,
    },
    retry_count: 0,
    max_retries: 1,
  };

  const root = admin.database().ref(`/homes/${homeId}`);
  await root.update({
    [`commands/pending/${commandId}`]: commandRecord,
    [`commands/history/${commandId}`]: commandRecord,
    [`commands/latest_by_device/${action.deviceId}`]: commandRecord,
    [`commands/${action.deviceId}/latest`]: {
      ...commandRecord,
      created_at: now,
      created_at_ms: now,
      created_at_iso: msToIso(now),
      source: "backend_automation",
    },
    [`devices/${action.deviceId}/command_in_progress`]: true,
    [`devices/${action.deviceId}/pending_command_id`]: commandId,
    [`devices/${action.deviceId}/pending_target_state`]: targetState(action.command),
    [`devices/${action.deviceId}/last_requested_state`]: targetState(action.command),
    [`devices/${action.deviceId}/last_command_status`]: "pending",
    [`devices/${action.deviceId}/last_command_message`]: "Automatic command accepted.",
    [`devices/${action.deviceId}/last_command`]: {
      status: "pending",
      user_message: null,
      error_code: null,
    },
  });

  const cooldownMs =
    typeof automation.cooldown_ms === "number"
      ? automation.cooldown_ms
      : action.deviceId === "breaker_02"
        ? 10 * 60 * 1000
        : 5 * 60 * 1000;
  const logId = `auto_${now}`;
  await root.update({
    [`automation_state/${action.deviceId}`]: {
      last_auto_action: action.command,
      last_auto_action_at_ms: now,
      cooldown_until_ms: now + cooldownMs,
    },
    [`automation_logs/${logId}`]: {
      log_id: logId,
      home_id: homeId,
      device_id: action.deviceId,
      device_name: action.deviceName,
      command: action.command,
      target_state: targetState(action.command),
      reason: action.reason,
      command_id: commandId,
      source: "backend_automation",
      created_at_ms: now,
      created_at_iso: msToIso(now),
    },
  });

  return true;
}

export async function handleSuggestedAction(
  homeId: string,
  action: SuggestedAction
): Promise<"manual_recommendation_only" | "assist_suggestion" | "auto_command" | "auto_not_allowed"> {
  const mode = await getControlMode(homeId);
  if (mode === "manual") {
    return "manual_recommendation_only";
  }
  if (mode === "assist") {
    await createActionSuggestion(homeId, action);
    return "assist_suggestion";
  }
  return (await tryCreateAutomaticCommand(homeId, action))
    ? "auto_command"
    : "auto_not_allowed";
}
