# PM1B horizon qualification before repricing models

Date: 2026-09-23. This audit uses only capture time, book validity, source/market identity and the already frozen PM1A decision opportunities. It reads neither terminal labels nor future midpoint *changes* to select a horizon. The exact source, PM0 audit and split SHA-256 values are in `results/polymarket_pm1b_v1/horizon_audit.json` (SHA-256 `b2531000a410ed5f54d050d12c430ee77ca3f9a60c7e30899a4f681924088a40`).

At each fixed decision time, a future book qualifies only if its collector capture is strictly **after** the decision and at/before decision+h, is no more than five seconds old at that future clock, and remains a valid two-sided unlocked/uncrossed Up-token book. No nearest-neighbor rule may select a book from after the future clock. Missing/stale/invalid future books are counted, not imputed. Target semantics are based on collector snapshots, not exchange event-time midpoints.

| Horizon | Train usable / PM1A opportunities | Dev usable / PM1A opportunities | Final usable / PM1A opportunities | Usable final markets |
| ---: | ---: | ---: | ---: | ---: |
| 5 seconds | 11,237 / 16,947 | 7,729 / 8,749 | 4,154 / 4,621 | 122 |
| **15 seconds** | **12,479 / 16,947** | **7,476 / 8,749** | **4,104 / 4,621** | **120** |
| 30 seconds | 12,435 / 16,947 | 7,488 / 8,749 | 4,067 / 4,621 | 121 |

The **15-second horizon** is frozen in `configs/polymarket_pm1b_v1.json`: it retains more train opportunities than 5 seconds while keeping almost all dev/final opportunities, and its horizon is shorter than the 30-second decision cadence. The choice used denominator/capture considerations only, not repricing values or model performance. At 15 seconds, usable train/dev/final opportunities span 5m (1,145/996/522), 15m (2,462/1,692/846), and 4h (8,872/4,788/2,736) contracts. Market-equal scoring is required because 4h contracts produce many more opportunities.

The planned target is future Up midpoint minus current midpoint in probability points, with B0 no-change baseline, current-state XGBoost, same-history XGBoost and same-information GRU. Primary metric is equal-market mean squared error with paired market bootstrap. This is a distinct transient-repricing question after PM1A's terminal-calibration null; even a positive PM1B result cannot be described as better terminal information or a tradable profit. The one partial final UTC day remains exploratory. No PM1B model has yet been fitted or final repricing value inspected at this audit checkpoint.
