# Polymarket settlement value and external BTC study

P1 is complete for the measurable subset. P2 source acceptance is complete with two semantic blockers; conditional model fitting is not permitted. Weather/Sports feasibility is still being assembled for the complete overnight deliverable.

## P1: gross value relative to settlement

Three exposed 08 UTC development hours only. The primary weighting is share-weighted within event, equal events within day, then equal days. Mean gross value is **-0.273206 cents/share**; pooling all shares gives **-0.735121 cents/share**. These values exclude inventory cost basis, fees, rebates, hedges, interim exits and capital costs. They are not maker account profit or avoidable adverse selection.

| UTC day | Active / measured events | Joined groups | Legs | Shares | Event-equal cents/share | Share-weighted cents/share |
|---|---:|---:|---:|---:|---:|---:|
| 2026-07-28 | 8 / 8 | 7179 | 15346 | 219429.284419 | 0.178156 | 0.272263 |
| 2026-07-29 | 11 / 11 | 14067 | 28647 | 554530.896809 | -0.915637 | -1.507844 |
| 2026-07-30 | 13 / 12 | 25246 | 50236 | 731865.993129 | -0.082138 | -0.451669 |

All 94,229 inherited joined legs connect to the verified both-token CTF identity and payout cache. No duplicate legs or group exclusions arose. Only the original 24 structural examples (41 legs) have independent input/receipt support; the remainder use the inherited event-derived mechanism. Cross-condition or unknown-token groups are rejected by the new analysis.

The original active denominator remains 32. One July 30 event has nine prints and no joined group; all nine are in the unjoined set. The three hours have 3 / 484 / 683 unjoined prints respectively. Their missing maker-leg quantities are unknown, so no population-wide loss bound is reported. There are no missing payments among measurable legs.

## Fixed strata and concentration

| Up-equivalent stratum | Events | Legs | Shares | Day-equal cents/share |
|---|---:|---:|---:|---:|
| up_equivalent_buy | 31 | 47793 | 710794.637428 | 6.960771268760058 |
| up_equivalent_sell | 31 | 46436 | 795031.536929 | -5.4828405488119065 |
| [.2,.4) | 21 | 16497 | 187909.123151 | 0.9556879635472382 |
| [.4,.6) | 28 | 21367 | 256514.809061 | -1.1583379469318091 |
| [.6,.8) | 20 | 14194 | 164874.042308 | -3.263655441674611 |
| [.8,1] | 17 | 23036 | 532440.762929 | -3.478706756787533 |
| [0,.2) | 16 | 19135 | 364087.436908 | 1.224258715940033 |

Strata overlap across events and are descriptive; directions and price bins are separate, not crossed into searched cells. Cells with fewer than five events do not establish a stable pattern. Full per-day strata, event aggregates and denominators are in `settlement_aggregate.json`.

Removing the largest-share event changes the primary value to **-0.200212 cents/share**. Removing the largest absolute total-value event changes it to **-0.505378 cents/share**; the same event also has the largest absolute contribution under primary weights. The largest event accounts for 11.10% of measured shares. These checks do not supply long-run confidence from three dates.

## Correctness and resources

Eleven focused synthetic tests pass: buy/sell arithmetic, complementary-token invariance, invalid inputs, fixed price boundaries, payout direction, hierarchical weights, unresolved payments, duplicate conflicts, taker exclusion, unknown-token quarantine and identical duplicate handling. Actual execution rechecked six frozen cache hashes. No hourly raw files or network responses were reread for P1. Cached input size: 111,314,096 bytes; scoring wall time 3.904 s and CPU 3.876 s, macOS peak process RSS 624,852,992 bytes. Preparation/tests are not included in that timed scorer.

Reproduction: run `python scripts/polymarket_settlement_value.py --repo . --public <new-aggregate-json> --private <private-row-json>` with the frozen private caches. The program refuses to replace outputs. Run `python tests/test_polymarket_settlement_value.py` for synthetic checks. Row-level values and identifiers remain private.

Original A remains `STOP / DATA_GATED`; old quantity expansion remains stopped. No independent final data were opened.
## P2：固定七天外部 BTC 信息

**状态：`NOT_FIT_EXTERNAL_SOURCE_SEMANTICS_UNKNOWN`。** 固定白名单包含 2026-07-27 至 2026-08-02 UTC 的 21 个 `BTCUSDT` depth Parquet 对象，合计 224,233,100 bytes；首对象 10,756,333 bytes，随后 20 个对象 213,476,767 bytes。数据获取累计 21 次成功请求，恢复验收复用全部缓存、0 次成功网络请求和 0 新下载。一次缓存根误配产生 3 次 DNS 前失败尝试、0 bytes，已单独计入资源收据；没有残留 `.part` 文件。

21 个对象 schema 一致，共 6,039,631 行。表内每行有 `bid1_px`–`bid10_px`、`ask1_px`–`ask10_px`、层数与更新时间字段；数值检查未发现交叉顶部、非有限顶部或层级价格顺序错误。这只能证明物理列结构，不能证明上游采集合同。随包 README 只说明快照日期范围、manifest 与下载方式，Parquet 没有字段元数据，也没有随包 collector 代码说明每行究竟是完整/partial depth snapshot，或由 Binance diff 更新重建/采样而来。因此 `bid1_px`/`ask1_px` 不能在本协议下自动升级为已核实的历史最优价，记为 `EXTERNAL_PRICE_SEMANTICS_UNKNOWN`。

候选整数时钟的量级与该周 UTC 相容，但 `ts_recv == ts_event` 在 6,039,631/6,039,631 行成立，且没有独立 collector clock contract 定义 `ts_recv`。这项观察不证明字段伪造，也不证明没有接收时钟；它只意味着无法按预注册要求把事件时间与历史接收时间区分开，记为 `EXTERNAL_CLOCK_UNKNOWN`。

仅作诊断，若同时假定 `bid1_px`/`ask1_px` 是有效顶部、`ts_recv` 是 Unix 毫秒历史接收时间，再按“锚点前最新原始行、年龄不超过 1,000 ms、最新无效不回捞、同接收时刻不同顶部判冲突”的固定规则连接原 1,942 个价格与 CTF 标签合格事件，则主锚点联合覆盖为：训练 811/812（99.88%）、校准 279/279（100%）、07-31 285/285（100%）、08-01 281/281（100%）、08-02 283/285（99.30%）。5 秒时移覆盖也均超过 80%。这些数值明确标为 `CONDITIONAL_ONLY`，不能解除两个来源语义门槛。

因此没有拟合 Eprice/Eexternal，也没有计算主 gain、Brier 或 5 秒敏感性。结论是具体来源语义阻塞，不是“外部 BTC 无信号”。S(s) 不是官方 strike，BTCUSDT 未被当作结算 BTC/USD，赢家仍只来自原 CTF 标签。冻结日期、1,942 分母、变量、C 候选、阈值与模型均未修改。四个 pytest 合成测试通过，覆盖未来报价、过期报价、最新无效不回捞、同接收时刻顶部冲突及冻结配置。
