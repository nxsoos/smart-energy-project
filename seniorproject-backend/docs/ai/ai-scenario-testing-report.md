# AI Scenario Testing Report

KahrabaIQ AI scenarios should be tested against the AWS-backed path store and the same home paths used by the phone app and Pi sync.

Recommended scenarios:

- Missing or stale sensor data returns a safe degraded result.
- High usage produces a recommendation with clear reasoning.
- Smoke or gas state prioritizes safety guidance over optimization.
- Occupancy changes influence comfort and energy suggestions.
- Daily and hourly summaries are read when available and ignored safely when absent.

Expected outputs should be validated through API responses and DynamoDB records.
