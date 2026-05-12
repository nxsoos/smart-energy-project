# KahrabaIQ Home Settings

Home settings are stored per home and are managed through the EC2 API:

```text
GET /api/home/{home_id}/settings
PUT /api/home/{home_id}/settings
```

Home admins can edit settings. Members and viewers can view the dashboard but cannot update settings. Platform admins can edit when backend role rules allow it.

Settings affect real behavior, not only UI:

- cost calculations use `cost_per_kwh`
- monthly and daily budget status use cost/energy limits
- cost and energy notifications use limit and warning thresholds
- AI receives budget, comfort, occupancy, stale/offline, notification, and automation settings
- AI recommendations, anomaly notifications, and cost forecast can be disabled
- occupancy detection uses motion, sound, empty-room, and confidence thresholds
- device, sensor, breaker, and hub status use configured stale/offline thresholds
- automatic control and schedules honor their enabled/disabled settings
- quiet hours mute non-urgent notifications while safety alerts remain urgent

Budget notifications are deduplicated by period, for example:

```text
COST_LIMIT#YYYY-MM#home_id
COST_WARNING#YYYY-MM#80#home_id
ENERGY_LIMIT#YYYY-MM#home_id
DAILY_COST_LIMIT#YYYY-MM-DD#home_id
```

Scenario mode uses temporary/default settings and must not save changes to the real home.

Future work:

- add a true deferred-notification delivery worker for quiet-hours queues
- sync effective cloud settings down to the Pi for fully local fallback behavior
- add more backend permission and notification unit tests with mocked storage
