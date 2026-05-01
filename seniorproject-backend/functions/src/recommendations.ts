import { admin } from "./firebase";
import type { RecommendationRecord, UpsertRecommendationInput } from "./types";

export async function upsertRecommendation(
  backendRef: admin.database.Reference,
  recommendationKey: string,
  input: UpsertRecommendationInput,
  timestampMs: number
): Promise<void> {
  const recommendationRef = backendRef.child(
    `recommendations/${recommendationKey}`
  );

  const existingSnap = await recommendationRef.get();

  if (existingSnap.exists()) {
    const existing = existingSnap.val() as Partial<RecommendationRecord>;

    await recommendationRef.update({
      recommendation_id:
        typeof existing.recommendation_id === "string"
          ? existing.recommendation_id
          : `rec_${timestampMs}`,
      type: input.type,
      priority: input.priority,
      title: input.title,
      message: input.message,
      source: input.source,
      related_device_id: input.related_device_id ?? null,
      related_alert_key: input.related_alert_key ?? null,
      status: "active",
      created_at:
        typeof existing.created_at === "number"
          ? existing.created_at
          : timestampMs,
      resolved_at: null,
      updated_at: timestampMs,
    });

    return;
  }

  const recommendation: RecommendationRecord = {
    recommendation_id: `rec_${timestampMs}`,
    type: input.type,
    priority: input.priority,
    title: input.title,
    message: input.message,
    source: input.source,
    related_device_id: input.related_device_id ?? null,
    related_alert_key: input.related_alert_key ?? null,
    status: "active",
    created_at: timestampMs,
    resolved_at: null,
    updated_at: timestampMs,
  };

  await recommendationRef.set(recommendation);
}

export async function resolveRecommendation(
  backendRef: admin.database.Reference,
  recommendationKey: string,
  timestampMs: number
): Promise<void> {
  const recommendationRef = backendRef.child(
    `recommendations/${recommendationKey}`
  );

  const recommendationSnap = await recommendationRef.get();

  if (!recommendationSnap.exists()) {
    return;
  }

  const recommendation = recommendationSnap.val() as Partial<RecommendationRecord>;

  if (recommendation.status === "resolved" && recommendation.resolved_at) {
    return;
  }

  await recommendationRef.update({
    status: "resolved",
    resolved_at: timestampMs,
    updated_at: timestampMs,
  });
}
