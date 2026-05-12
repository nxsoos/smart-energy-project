# KahrabaIQ Smart Energy AI Evaluation

Generated at: 2026-05-12T00:46:04Z
Model version: 2

## Dataset

- Full rows: 199
- Train rows: 840
- Validation rows: 160
- Test rows: 199
- Feature count: 77
- Data origin counts: `{"synthetic_scenario": 199}`

## Selected Models

- `waste_event`: GradientBoosting
- `anomaly_label`: GradientBoosting
- `recommendation_type`: HistGradientBoosting
- `next_hour_total_energy_kWh`: ExtraTrees
- `next_hour_total_cost_BHD`: ExtraTrees

## Test Metrics

### waste_event

```json
{
  "accuracy": 0.9799,
  "precision_macro": 0.9805,
  "recall_macro": 0.9793,
  "f1_macro": 0.9798,
  "f1_weighted": 0.9799,
  "per_class": {
    "False": {
      "precision": 0.9891304347826086,
      "recall": 0.9680851063829787,
      "f1-score": 0.978494623655914,
      "support": 94.0
    },
    "True": {
      "precision": 0.9719626168224299,
      "recall": 0.9904761904761905,
      "f1-score": 0.9811320754716981,
      "support": 105.0
    },
    "micro avg": {
      "precision": 0.9798994974874372,
      "recall": 0.9798994974874372,
      "f1-score": 0.9798994974874372,
      "support": 199.0
    },
    "macro avg": {
      "precision": 0.9805465258025192,
      "recall": 0.9792806484295846,
      "f1-score": 0.9798133495638061,
      "support": 199.0
    },
    "weighted avg": {
      "precision": 0.980072038371459,
      "recall": 0.9798994974874372,
      "f1-score": 0.9798862439607249,
      "support": 199.0
    }
  },
  "special_recall": {}
}
```

### anomaly_label

```json
{
  "accuracy": 0.9698,
  "precision_macro": 0.8444,
  "recall_macro": 0.875,
  "f1_macro": 0.8574,
  "f1_weighted": 0.9617,
  "per_class": {
    "ac_running_empty_room": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 31.0
    },
    "high_temperature_comfort": {
      "precision": 0.0,
      "recall": 0.0,
      "f1-score": 0.0,
      "support": 4.0
    },
    "hub_offline_or_stale": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "low_usage_normal": {
      "precision": 0.5714285714285714,
      "recall": 0.8,
      "f1-score": 0.6666666666666666,
      "support": 5.0
    },
    "normal": {
      "precision": 0.8888888888888888,
      "recall": 1.0,
      "f1-score": 0.9411764705882353,
      "support": 16.0
    },
    "possible_sensor_stale": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "smoke_gas_safety": {
      "precision": 1.0,
      "recall": 0.95,
      "f1-score": 0.9743589743589743,
      "support": 20.0
    },
    "socket_left_on": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "sudden_power_spike": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 3.0
    },
    "unusual_same_hour_usage": {
      "precision": 0.9836065573770492,
      "recall": 1.0,
      "f1-score": 0.9917355371900827,
      "support": 60.0
    },
    "accuracy": 0.9698492462311558,
    "macro avg": {
      "precision": 0.844392401769451,
      "recall": 0.875,
      "f1-score": 0.8573937648803959,
      "support": 199.0
    },
    "weighted avg": {
      "precision": 0.9552550679496886,
      "recall": 0.9698492462311558,
      "f1-score": 0.9617259727705002,
      "support": 199.0
    }
  },
  "special_recall": {
    "smoke_gas_safety": 0.95,
    "ac_running_empty_room": 1.0,
    "socket_left_on": 1.0,
    "unusual_same_hour_usage": 1.0
  }
}
```

### recommendation_type

```json
{
  "accuracy": 0.9799,
  "precision_macro": 0.9409,
  "recall_macro": 0.9471,
  "f1_macro": 0.942,
  "f1_weighted": 0.9805,
  "per_class": {
    "check_sensor_connection": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "check_smoke_gas_sensor": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "keep_monitoring": {
      "precision": 1.0,
      "recall": 0.8571428571428571,
      "f1-score": 0.9230769230769231,
      "support": 21.0
    },
    "reduce_peak_load": {
      "precision": 0.5,
      "recall": 0.6666666666666666,
      "f1-score": 0.5714285714285714,
      "support": 3.0
    },
    "review_unusual_usage": {
      "precision": 0.967741935483871,
      "recall": 1.0,
      "f1-score": 0.9836065573770492,
      "support": 60.0
    },
    "turn_off_or_adjust_ac": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 31.0
    },
    "turn_off_unused_socket": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "verify_occupancy": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 4.0
    },
    "wait_for_fresh_data": {
      "precision": 1.0,
      "recall": 1.0,
      "f1-score": 1.0,
      "support": 20.0
    },
    "accuracy": 0.9798994974874372,
    "macro avg": {
      "precision": 0.9408602150537635,
      "recall": 0.9470899470899471,
      "f1-score": 0.9420124502091716,
      "support": 199.0
    },
    "weighted avg": {
      "precision": 0.9827362619549359,
      "recall": 0.9798994974874372,
      "f1-score": 0.9804788670428345,
      "support": 199.0
    }
  },
  "special_recall": {}
}
```

### next_hour_total_energy_kWh

```json
{
  "mae": 0.069873,
  "rmse": 0.096881,
  "r2": 0.1202,
  "mean_actual": 0.09913,
  "mean_predicted": 0.086658,
  "error_summary": {
    "p50_abs_error": 0.050255,
    "p90_abs_error": 0.149794,
    "max_abs_error": 0.333324
  }
}
```

### next_hour_total_cost_BHD

```json
{
  "mae": 0.002233,
  "rmse": 0.003094,
  "r2": 0.1235,
  "mean_actual": 0.003172,
  "mean_predicted": 0.00278,
  "error_summary": {
    "p50_abs_error": 0.00159,
    "p90_abs_error": 0.004741,
    "max_abs_error": 0.010637
  }
}
```

## Segment Metrics

### all_test_data

```json
{
  "rows": 199,
  "waste_event": {
    "accuracy": 0.9799,
    "precision_macro": 0.9805,
    "recall_macro": 0.9793,
    "f1_macro": 0.9798,
    "f1_weighted": 0.9799,
    "per_class": {
      "False": {
        "precision": 0.9891304347826086,
        "recall": 0.9680851063829787,
        "f1-score": 0.978494623655914,
        "support": 94.0
      },
      "True": {
        "precision": 0.9719626168224299,
        "recall": 0.9904761904761905,
        "f1-score": 0.9811320754716981,
        "support": 105.0
      },
      "micro avg": {
        "precision": 0.9798994974874372,
        "recall": 0.9798994974874372,
        "f1-score": 0.9798994974874372,
        "support": 199.0
      },
      "macro avg": {
        "precision": 0.9805465258025192,
        "recall": 0.9792806484295846,
        "f1-score": 0.9798133495638061,
        "support": 199.0
      },
      "weighted avg": {
        "precision": 0.980072038371459,
        "recall": 0.9798994974874372,
        "f1-score": 0.9798862439607249,
        "support": 199.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 0.9698,
    "precision_macro": 0.8444,
    "recall_macro": 0.875,
    "f1_macro": 0.8574,
    "f1_weighted": 0.9617,
    "per_class": {
      "ac_running_empty_room": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 31.0
      },
      "high_temperature_comfort": {
        "precision": 0.0,
        "recall": 0.0,
        "f1-score": 0.0,
        "support": 4.0
      },
      "hub_offline_or_stale": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "low_usage_normal": {
        "precision": 0.5714285714285714,
        "recall": 0.8,
        "f1-score": 0.6666666666666666,
        "support": 5.0
      },
      "normal": {
        "precision": 0.8888888888888888,
        "recall": 1.0,
        "f1-score": 0.9411764705882353,
        "support": 16.0
      },
      "possible_sensor_stale": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "smoke_gas_safety": {
        "precision": 1.0,
        "recall": 0.95,
        "f1-score": 0.9743589743589743,
        "support": 20.0
      },
      "socket_left_on": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "sudden_power_spike": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 3.0
      },
      "unusual_same_hour_usage": {
        "precision": 0.9836065573770492,
        "recall": 1.0,
        "f1-score": 0.9917355371900827,
        "support": 60.0
      },
      "accuracy": 0.9698492462311558,
      "macro avg": {
        "precision": 0.844392401769451,
        "recall": 0.875,
        "f1-score": 0.8573937648803959,
        "support": 199.0
      },
      "weighted avg": {
        "precision": 0.9552550679496886,
        "recall": 0.9698492462311558,
        "f1-score": 0.9617259727705002,
        "support": 199.0
      }
    },
    "special_recall": {
      "smoke_gas_safety": 0.95,
      "ac_running_empty_room": 1.0,
      "socket_left_on": 1.0,
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 0.9799,
    "precision_macro": 0.9409,
    "recall_macro": 0.9471,
    "f1_macro": 0.942,
    "f1_weighted": 0.9805,
    "per_class": {
      "check_sensor_connection": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "check_smoke_gas_sensor": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "keep_monitoring": {
        "precision": 1.0,
        "recall": 0.8571428571428571,
        "f1-score": 0.9230769230769231,
        "support": 21.0
      },
      "reduce_peak_load": {
        "precision": 0.5,
        "recall": 0.6666666666666666,
        "f1-score": 0.5714285714285714,
        "support": 3.0
      },
      "review_unusual_usage": {
        "precision": 0.967741935483871,
        "recall": 1.0,
        "f1-score": 0.9836065573770492,
        "support": 60.0
      },
      "turn_off_or_adjust_ac": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 31.0
      },
      "turn_off_unused_socket": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "verify_occupancy": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 4.0
      },
      "wait_for_fresh_data": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 0.9798994974874372,
      "macro avg": {
        "precision": 0.9408602150537635,
        "recall": 0.9470899470899471,
        "f1-score": 0.9420124502091716,
        "support": 199.0
      },
      "weighted avg": {
        "precision": 0.9827362619549359,
        "recall": 0.9798994974874372,
        "f1-score": 0.9804788670428345,
        "support": 199.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.069873,
    "rmse": 0.096881,
    "r2": 0.1202,
    "mean_actual": 0.09913,
    "mean_predicted": 0.086658,
    "error_summary": {
      "p50_abs_error": 0.050255,
      "p90_abs_error": 0.149794,
      "max_abs_error": 0.333324
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.002233,
    "rmse": 0.003094,
    "r2": 0.1235,
    "mean_actual": 0.003172,
    "mean_predicted": 0.00278,
    "error_summary": {
      "p50_abs_error": 0.00159,
      "p90_abs_error": 0.004741,
      "max_abs_error": 0.010637
    }
  }
}
```

### origin:synthetic_scenario

```json
{
  "rows": 199,
  "waste_event": {
    "accuracy": 0.9799,
    "precision_macro": 0.9805,
    "recall_macro": 0.9793,
    "f1_macro": 0.9798,
    "f1_weighted": 0.9799,
    "per_class": {
      "False": {
        "precision": 0.9891304347826086,
        "recall": 0.9680851063829787,
        "f1-score": 0.978494623655914,
        "support": 94.0
      },
      "True": {
        "precision": 0.9719626168224299,
        "recall": 0.9904761904761905,
        "f1-score": 0.9811320754716981,
        "support": 105.0
      },
      "micro avg": {
        "precision": 0.9798994974874372,
        "recall": 0.9798994974874372,
        "f1-score": 0.9798994974874372,
        "support": 199.0
      },
      "macro avg": {
        "precision": 0.9805465258025192,
        "recall": 0.9792806484295846,
        "f1-score": 0.9798133495638061,
        "support": 199.0
      },
      "weighted avg": {
        "precision": 0.980072038371459,
        "recall": 0.9798994974874372,
        "f1-score": 0.9798862439607249,
        "support": 199.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 0.9698,
    "precision_macro": 0.8444,
    "recall_macro": 0.875,
    "f1_macro": 0.8574,
    "f1_weighted": 0.9617,
    "per_class": {
      "ac_running_empty_room": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 31.0
      },
      "high_temperature_comfort": {
        "precision": 0.0,
        "recall": 0.0,
        "f1-score": 0.0,
        "support": 4.0
      },
      "hub_offline_or_stale": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "low_usage_normal": {
        "precision": 0.5714285714285714,
        "recall": 0.8,
        "f1-score": 0.6666666666666666,
        "support": 5.0
      },
      "normal": {
        "precision": 0.8888888888888888,
        "recall": 1.0,
        "f1-score": 0.9411764705882353,
        "support": 16.0
      },
      "possible_sensor_stale": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "smoke_gas_safety": {
        "precision": 1.0,
        "recall": 0.95,
        "f1-score": 0.9743589743589743,
        "support": 20.0
      },
      "socket_left_on": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "sudden_power_spike": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 3.0
      },
      "unusual_same_hour_usage": {
        "precision": 0.9836065573770492,
        "recall": 1.0,
        "f1-score": 0.9917355371900827,
        "support": 60.0
      },
      "accuracy": 0.9698492462311558,
      "macro avg": {
        "precision": 0.844392401769451,
        "recall": 0.875,
        "f1-score": 0.8573937648803959,
        "support": 199.0
      },
      "weighted avg": {
        "precision": 0.9552550679496886,
        "recall": 0.9698492462311558,
        "f1-score": 0.9617259727705002,
        "support": 199.0
      }
    },
    "special_recall": {
      "smoke_gas_safety": 0.95,
      "ac_running_empty_room": 1.0,
      "socket_left_on": 1.0,
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 0.9799,
    "precision_macro": 0.9409,
    "recall_macro": 0.9471,
    "f1_macro": 0.942,
    "f1_weighted": 0.9805,
    "per_class": {
      "check_sensor_connection": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "check_smoke_gas_sensor": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "keep_monitoring": {
        "precision": 1.0,
        "recall": 0.8571428571428571,
        "f1-score": 0.9230769230769231,
        "support": 21.0
      },
      "reduce_peak_load": {
        "precision": 0.5,
        "recall": 0.6666666666666666,
        "f1-score": 0.5714285714285714,
        "support": 3.0
      },
      "review_unusual_usage": {
        "precision": 0.967741935483871,
        "recall": 1.0,
        "f1-score": 0.9836065573770492,
        "support": 60.0
      },
      "turn_off_or_adjust_ac": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 31.0
      },
      "turn_off_unused_socket": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "verify_occupancy": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 4.0
      },
      "wait_for_fresh_data": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 0.9798994974874372,
      "macro avg": {
        "precision": 0.9408602150537635,
        "recall": 0.9470899470899471,
        "f1-score": 0.9420124502091716,
        "support": 199.0
      },
      "weighted avg": {
        "precision": 0.9827362619549359,
        "recall": 0.9798994974874372,
        "f1-score": 0.9804788670428345,
        "support": 199.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.069873,
    "rmse": 0.096881,
    "r2": 0.1202,
    "mean_actual": 0.09913,
    "mean_predicted": 0.086658,
    "error_summary": {
      "p50_abs_error": 0.050255,
      "p90_abs_error": 0.149794,
      "max_abs_error": 0.333324
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.002233,
    "rmse": 0.003094,
    "r2": 0.1235,
    "mean_actual": 0.003172,
    "mean_predicted": 0.00278,
    "error_summary": {
      "p50_abs_error": 0.00159,
      "p90_abs_error": 0.004741,
      "max_abs_error": 0.010637
    }
  }
}
```

### scenario_family:ac_left_on

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "True": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "ac_running_empty_room": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {
      "ac_running_empty_room": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "turn_off_or_adjust_ac": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.088705,
    "rmse": 0.105578,
    "r2": -0.1263,
    "mean_actual": 0.153728,
    "mean_predicted": 0.111447,
    "error_summary": {
      "p50_abs_error": 0.086258,
      "p90_abs_error": 0.121621,
      "max_abs_error": 0.273115
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.002799,
    "rmse": 0.003335,
    "r2": -0.0978,
    "mean_actual": 0.004919,
    "mean_predicted": 0.003604,
    "error_summary": {
      "p50_abs_error": 0.002813,
      "p90_abs_error": 0.003814,
      "max_abs_error": 0.008495
    }
  }
}
```

### scenario_family:high_energy

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "True": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "ac_running_empty_room": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 2.0
      },
      "unusual_same_hour_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 18.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {
      "ac_running_empty_room": 1.0,
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "review_unusual_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 18.0
      },
      "turn_off_or_adjust_ac": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 2.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.13201,
    "rmse": 0.152448,
    "r2": -0.4205,
    "mean_actual": 0.216024,
    "mean_predicted": 0.141439,
    "error_summary": {
      "p50_abs_error": 0.13355,
      "p90_abs_error": 0.208341,
      "max_abs_error": 0.331655
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.004201,
    "rmse": 0.004862,
    "r2": -0.4107,
    "mean_actual": 0.006913,
    "mean_predicted": 0.004558,
    "error_summary": {
      "p50_abs_error": 0.004254,
      "p90_abs_error": 0.006736,
      "max_abs_error": 0.010254
    }
  }
}
```

### scenario_family:hub_offline

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "False": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "hub_offline_or_stale": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "wait_for_fresh_data": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.044977,
    "rmse": 0.082002,
    "r2": -0.2011,
    "mean_actual": 0.050796,
    "mean_predicted": 0.054542,
    "error_summary": {
      "p50_abs_error": 0.030632,
      "p90_abs_error": 0.057053,
      "max_abs_error": 0.333324
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.001415,
    "rmse": 0.002612,
    "r2": -0.19,
    "mean_actual": 0.001625,
    "mean_predicted": 0.001733,
    "error_summary": {
      "p50_abs_error": 0.001027,
      "p90_abs_error": 0.001806,
      "max_abs_error": 0.010637
    }
  }
}
```

### scenario_family:low_usage_normal

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "False": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 0.75,
    "precision_macro": 0.6012,
    "recall_macro": 0.7,
    "f1_macro": 0.6439,
    "f1_weighted": 0.6712,
    "per_class": {
      "high_temperature_comfort": {
        "precision": 0.0,
        "recall": 0.0,
        "f1-score": 0.0,
        "support": 4.0
      },
      "low_usage_normal": {
        "precision": 0.5714285714285714,
        "recall": 0.8,
        "f1-score": 0.6666666666666666,
        "support": 5.0
      },
      "normal": {
        "precision": 0.8333333333333334,
        "recall": 1.0,
        "f1-score": 0.9090909090909091,
        "support": 10.0
      },
      "unusual_same_hour_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 1.0
      },
      "accuracy": 0.75,
      "macro avg": {
        "precision": 0.6011904761904762,
        "recall": 0.7,
        "f1-score": 0.6439393939393939,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 0.6095238095238095,
        "recall": 0.75,
        "f1-score": 0.6712121212121211,
        "support": 20.0
      }
    },
    "special_recall": {
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "keep_monitoring": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 15.0
      },
      "review_unusual_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 1.0
      },
      "verify_occupancy": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 4.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.100124,
    "rmse": 0.130726,
    "r2": -0.1904,
    "mean_actual": 0.0813,
    "mean_predicted": 0.073389,
    "error_summary": {
      "p50_abs_error": 0.079543,
      "p90_abs_error": 0.215392,
      "max_abs_error": 0.316447
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.003228,
    "rmse": 0.004201,
    "r2": -0.2002,
    "mean_actual": 0.002602,
    "mean_predicted": 0.002354,
    "error_summary": {
      "p50_abs_error": 0.002462,
      "p90_abs_error": 0.006934,
      "max_abs_error": 0.010058
    }
  }
}
```

### scenario_family:normal_usage

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 0.85,
    "precision_macro": 0.8333,
    "recall_macro": 0.8929,
    "f1_macro": 0.84,
    "f1_weighted": 0.856,
    "per_class": {
      "False": {
        "precision": 1.0,
        "recall": 0.7857142857142857,
        "f1-score": 0.88,
        "support": 14.0
      },
      "True": {
        "precision": 0.6666666666666666,
        "recall": 1.0,
        "f1-score": 0.8,
        "support": 6.0
      },
      "micro avg": {
        "precision": 0.85,
        "recall": 0.85,
        "f1-score": 0.85,
        "support": 20.0
      },
      "macro avg": {
        "precision": 0.8333333333333333,
        "recall": 0.8928571428571428,
        "f1-score": 0.8400000000000001,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 0.9,
        "recall": 0.85,
        "f1-score": 0.8560000000000001,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "normal": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 6.0
      },
      "sudden_power_spike": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 3.0
      },
      "unusual_same_hour_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 11.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 0.8,
    "precision_macro": 0.7821,
    "recall_macro": 0.7222,
    "f1_macro": 0.7183,
    "f1_weighted": 0.7899,
    "per_class": {
      "keep_monitoring": {
        "precision": 1.0,
        "recall": 0.5,
        "f1-score": 0.6666666666666666,
        "support": 6.0
      },
      "reduce_peak_load": {
        "precision": 0.5,
        "recall": 0.6666666666666666,
        "f1-score": 0.5714285714285714,
        "support": 3.0
      },
      "review_unusual_usage": {
        "precision": 0.8461538461538461,
        "recall": 1.0,
        "f1-score": 0.9166666666666666,
        "support": 11.0
      },
      "accuracy": 0.8,
      "macro avg": {
        "precision": 0.782051282051282,
        "recall": 0.7222222222222222,
        "f1-score": 0.7182539682539683,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 0.8403846153846153,
        "recall": 0.8,
        "f1-score": 0.7898809523809524,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.061551,
    "rmse": 0.083409,
    "r2": -0.1096,
    "mean_actual": 0.070753,
    "mean_predicted": 0.064413,
    "error_summary": {
      "p50_abs_error": 0.046198,
      "p90_abs_error": 0.100293,
      "max_abs_error": 0.248955
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.001968,
    "rmse": 0.002683,
    "r2": -0.121,
    "mean_actual": 0.002264,
    "mean_predicted": 0.002025,
    "error_summary": {
      "p50_abs_error": 0.001434,
      "p90_abs_error": 0.003521,
      "max_abs_error": 0.007995
    }
  }
}
```

### scenario_family:power_spike

```json
{
  "rows": 19,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "True": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "ac_running_empty_room": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 3.0
      },
      "unusual_same_hour_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 16.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      }
    },
    "special_recall": {
      "ac_running_empty_room": 1.0,
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "review_unusual_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 16.0
      },
      "turn_off_or_adjust_ac": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 3.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 19.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.064525,
    "rmse": 0.085358,
    "r2": -0.0736,
    "mean_actual": 0.14353,
    "mean_predicted": 0.124497,
    "error_summary": {
      "p50_abs_error": 0.051031,
      "p90_abs_error": 0.131089,
      "max_abs_error": 0.21464
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.002121,
    "rmse": 0.002736,
    "r2": -0.0776,
    "mean_actual": 0.004593,
    "mean_predicted": 0.003954,
    "error_summary": {
      "p50_abs_error": 0.001764,
      "p90_abs_error": 0.004585,
      "max_abs_error": 0.006288
    }
  }
}
```

### scenario_family:routine_anomaly

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 0.95,
    "precision_macro": 0.5,
    "recall_macro": 0.475,
    "f1_macro": 0.4872,
    "f1_weighted": 0.9744,
    "per_class": {
      "False": {
        "precision": 0.0,
        "recall": 0.0,
        "f1-score": 0.0,
        "support": 0.0
      },
      "True": {
        "precision": 1.0,
        "recall": 0.95,
        "f1-score": 0.9743589743589743,
        "support": 20.0
      },
      "micro avg": {
        "precision": 0.95,
        "recall": 0.95,
        "f1-score": 0.95,
        "support": 20.0
      },
      "macro avg": {
        "precision": 0.5,
        "recall": 0.475,
        "f1-score": 0.48717948717948717,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 0.95,
        "f1-score": 0.9743589743589742,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "ac_running_empty_room": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 6.0
      },
      "unusual_same_hour_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 14.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {
      "ac_running_empty_room": 1.0,
      "unusual_same_hour_usage": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "review_unusual_usage": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 14.0
      },
      "turn_off_or_adjust_ac": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 6.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.045023,
    "rmse": 0.054664,
    "r2": 0.21,
    "mean_actual": 0.098067,
    "mean_predicted": 0.108921,
    "error_summary": {
      "p50_abs_error": 0.041349,
      "p90_abs_error": 0.083388,
      "max_abs_error": 0.117993
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.001411,
    "rmse": 0.001741,
    "r2": 0.2172,
    "mean_actual": 0.003138,
    "mean_predicted": 0.003497,
    "error_summary": {
      "p50_abs_error": 0.001307,
      "p90_abs_error": 0.002695,
      "max_abs_error": 0.003716
    }
  }
}
```

### scenario_family:smoke_gas

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "False": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 0.95,
    "precision_macro": 0.5,
    "recall_macro": 0.475,
    "f1_macro": 0.4872,
    "f1_weighted": 0.9744,
    "per_class": {
      "smoke_gas_safety": {
        "precision": 1.0,
        "recall": 0.95,
        "f1-score": 0.9743589743589743,
        "support": 20.0
      },
      "unusual_same_hour_usage": {
        "precision": 0.0,
        "recall": 0.0,
        "f1-score": 0.0,
        "support": 0.0
      },
      "accuracy": 0.95,
      "macro avg": {
        "precision": 0.5,
        "recall": 0.475,
        "f1-score": 0.48717948717948717,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 0.95,
        "f1-score": 0.9743589743589742,
        "support": 20.0
      }
    },
    "special_recall": {
      "smoke_gas_safety": 0.95,
      "unusual_same_hour_usage": 0.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "check_smoke_gas_sensor": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.057414,
    "rmse": 0.06549,
    "r2": -0.1346,
    "mean_actual": 0.049846,
    "mean_predicted": 0.079585,
    "error_summary": {
      "p50_abs_error": 0.043497,
      "p90_abs_error": 0.105312,
      "max_abs_error": 0.125978
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.001832,
    "rmse": 0.002104,
    "r2": -0.1438,
    "mean_actual": 0.001595,
    "mean_predicted": 0.002555,
    "error_summary": {
      "p50_abs_error": 0.001342,
      "p90_abs_error": 0.003416,
      "max_abs_error": 0.003863
    }
  }
}
```

### scenario_family:socket_left_on

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "True": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "socket_left_on": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {
      "socket_left_on": 1.0
    }
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "turn_off_unused_socket": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.046951,
    "rmse": 0.077342,
    "r2": -0.1816,
    "mean_actual": 0.058963,
    "mean_predicted": 0.0556,
    "error_summary": {
      "p50_abs_error": 0.02079,
      "p90_abs_error": 0.080683,
      "max_abs_error": 0.275636
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.001485,
    "rmse": 0.00245,
    "r2": -0.158,
    "mean_actual": 0.001887,
    "mean_predicted": 0.001798,
    "error_summary": {
      "p50_abs_error": 0.000676,
      "p90_abs_error": 0.002489,
      "max_abs_error": 0.0087
    }
  }
}
```

### scenario_family:stale_data

```json
{
  "rows": 20,
  "waste_event": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "False": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "micro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "anomaly_label": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "possible_sensor_stale": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "recommendation_type": {
    "accuracy": 1.0,
    "precision_macro": 1.0,
    "recall_macro": 1.0,
    "f1_macro": 1.0,
    "f1_weighted": 1.0,
    "per_class": {
      "check_sensor_connection": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "accuracy": 1.0,
      "macro avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      },
      "weighted avg": {
        "precision": 1.0,
        "recall": 1.0,
        "f1-score": 1.0,
        "support": 20.0
      }
    },
    "special_recall": {}
  },
  "next_hour_total_energy_kWh": {
    "mae": 0.057186,
    "rmse": 0.08973,
    "r2": -0.0382,
    "mean_actual": 0.070516,
    "mean_predicted": 0.054638,
    "error_summary": {
      "p50_abs_error": 0.0308,
      "p90_abs_error": 0.149769,
      "max_abs_error": 0.281046
    }
  },
  "next_hour_total_cost_BHD": {
    "mae": 0.001864,
    "rmse": 0.002876,
    "r2": -0.0418,
    "mean_actual": 0.002256,
    "mean_predicted": 0.001783,
    "error_summary": {
      "p50_abs_error": 0.000967,
      "p90_abs_error": 0.004783,
      "max_abs_error": 0.008949
    }
  }
}
```

## Limitations

Because real collected data is limited, the current model is trained using real prototype data plus synthetic scenario data. Metrics on synthetic data show behavior coverage, not guaranteed real-world accuracy.

KahrabaIQ currently uses weakly supervised labels generated from transparent domain rules. This is suitable for a prototype and allows the system to train on collected smart-home data, but future work should include manually labeled events from real users to improve accuracy and reduce bias.