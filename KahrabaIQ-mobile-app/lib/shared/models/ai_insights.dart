class AiDashboardSummary {
  final DateTime updatedAt;
  final String source;
  final String modelName;
  final String modelVersion;
  final String inputSource;
  final bool energyWaste;
  final double wasteConfidence;
  final bool abnormalUsage;
  final double abnormalUsageConfidence;
  final String recommendationType;
  final String statusCode;
  final String statusLabel;
  final String statusTone;
  final String statusSummary;
  final String actionTitle;
  final double nextHourEnergyKwh;
  final double nextHourCostBhd;
  final double efficiencyScore;
  final String explanation;
  final String controlSuggestion;

  const AiDashboardSummary({
    required this.updatedAt,
    required this.source,
    required this.modelName,
    required this.modelVersion,
    required this.inputSource,
    required this.energyWaste,
    required this.wasteConfidence,
    required this.abnormalUsage,
    required this.abnormalUsageConfidence,
    required this.recommendationType,
    required this.statusCode,
    required this.statusLabel,
    required this.statusTone,
    required this.statusSummary,
    required this.actionTitle,
    required this.nextHourEnergyKwh,
    required this.nextHourCostBhd,
    required this.efficiencyScore,
    required this.explanation,
    required this.controlSuggestion,
  });
}

class AiDailySummary {
  final String dayId;
  final DateTime updatedAt;
  final String source;
  final int predictionCount;
  final int wastePredictionCount;
  final int abnormalPredictionCount;
  final double averageEfficiencyScore;
  final double predictedNextHourEnergyTotalKwh;
  final double predictedNextHourCostTotalBhd;
  final String latestExplanation;
  final String summary;

  const AiDailySummary({
    required this.dayId,
    required this.updatedAt,
    required this.source,
    required this.predictionCount,
    required this.wastePredictionCount,
    required this.abnormalPredictionCount,
    required this.averageEfficiencyScore,
    required this.predictedNextHourEnergyTotalKwh,
    required this.predictedNextHourCostTotalBhd,
    required this.latestExplanation,
    required this.summary,
  });
}

class AiRecommendation {
  final String recommendationId;
  final String type;
  final String priority;
  final String title;
  final String message;
  final String source;
  final String? relatedDeviceId;
  final String? relatedAlertKey;
  final String? aiPredictionId;
  final String recommendationType;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime? resolvedAt;

  const AiRecommendation({
    required this.recommendationId,
    required this.type,
    required this.priority,
    required this.title,
    required this.message,
    required this.source,
    this.relatedDeviceId,
    this.relatedAlertKey,
    this.aiPredictionId,
    required this.recommendationType,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.resolvedAt,
  });

  bool get isActive => status.toLowerCase() == 'active';
}

class AiAlertInsight {
  final String id;
  final String type;
  final String priority;
  final String title;
  final String message;
  final String source;
  final DateTime createdAt;
  final DateTime updatedAt;
  final bool energyWaste;
  final bool abnormalUsage;

  const AiAlertInsight({
    required this.id,
    required this.type,
    required this.priority,
    required this.title,
    required this.message,
    required this.source,
    required this.createdAt,
    required this.updatedAt,
    required this.energyWaste,
    required this.abnormalUsage,
  });
}

class AiNotification {
  final String id;
  final String homeId;
  final String severity;
  final String category;
  final String title;
  final String message;
  final String? deviceId;
  final String? targetType;
  final String? recommendationType;
  final DateTime createdAt;
  final bool acknowledged;
  final String source;
  final double? confidence;
  final String? explanation;

  const AiNotification({
    required this.id,
    required this.homeId,
    required this.severity,
    required this.category,
    required this.title,
    required this.message,
    this.deviceId,
    this.targetType,
    this.recommendationType,
    required this.createdAt,
    required this.acknowledged,
    required this.source,
    this.confidence,
    this.explanation,
  });

  bool get isCritical => severity.toLowerCase() == 'critical';
  bool get isAlert => {'high', 'critical'}.contains(severity.toLowerCase());
  bool get isSuggestion => category.toLowerCase() == 'recommendation';
}
