# Polymarket BTC-5m：缓存结算与七天评分收尾

**结论：`STOP_QUANTITY_INCREMENT`。** 固定 2026-07-27 至 2026-08-02 UTC 的全部 2016 个候选事件保留。
R3 相对 R2 的三个检查日日等权 log-loss gain 为 **-0.005868 nats/事件**（`LL(R2)−LL(R3)`，正数为数量有帮助），1/3 日为正。原继续研究门槛未全部通过，本协议下停止扩展数量增量模型。不能据此证明额外信息不存在。

这是 `RETROSPECTIVE_OFFLINE` 的开发比较，三个晚段日期并非独立 final。标签公开时刻和历史规则版本未知；所有特征保持原提取表，当前结算状态不回填为历史特征。Quote-or-Pull A 仍为 **`STOP / DATA_GATED`**。

## 缓存、身份和支付

旧缓存经冻结请求顺序重建语义键，复用 collection **790**、position **790**、payout **3025** 个有效响应，非法旧响应 0。原 1621 个事件的日索引仅证明 condition 归属；本次补齐双 token 的 CTF collection/position 对应，逐事件确定 Up 的 outcome index。最终标签状态：`{"identity_verified": 2016, "verified_binary": 2016}`。

新增 **9683** 个逻辑子调用、**389** 次 HTTP、**175** 个重试子调用、**1020523** 字节响应；剩余查询 **0**。历史 9976–10000 次请求区间原样保留。本次预算为 30000 子调用 / 2000 HTTP / 512 MiB，独立持久记账。成功缓存按 chain、contract、method/calldata、condition/index、block tag 和来源版本识别；发送前原子计费，失败项单独有限重试，单写入者限速。

支付只由已核实方向和完整分子/分母决定；缩放后的等价二元支付一致处理，Gamma 当前价格仅作差异诊断。CTF 的 [reportPayouts 合约](https://github.com/gnosis/conditional-tokens-contracts/blob/master/contracts/ConditionalTokens.sol) 在分母已设置后拒绝再次报告；因此复用旧已完成的非零结算响应。方向使用同一部署的 getCollectionId/getPositionId（零 parent、USDC.e collateral、index sets 1/2），对应 [CTHelpers](https://github.com/gnosis/conditional-tokens-contracts/blob/master/contracts/CTHelpers.sol)。既有与本次调用都是 latest，未记录具体块号，不能称同一块的快照。原始回复、逐事件身份/标签/预测全部私有。

## 全分母和原样本门槛

| UTC 日 | 角色 | 候选 | 二元标签 | 合格报价+标签 | 0 / 1 | 合格数量 | 30 秒历史 |
|---|---|---:|---:|---:|---:|---:|---:|
| 2026-07-27 | train | 288 | 288 | 280 | 153 / 127 | 280 | 278 |
| 2026-07-28 | train | 288 | 288 | 255 | 131 / 124 | 250 | 252 |
| 2026-07-29 | train | 288 | 288 | 277 | 133 / 144 | 277 | 273 |
| 2026-07-30 | calibration | 288 | 288 | 279 | 141 / 138 | 278 | 277 |
| 2026-07-31 | forward | 288 | 288 | 285 | 152 / 133 | 285 | 283 |
| 2026-08-01 | forward | 288 | 288 | 281 | 136 / 145 | 281 | 279 |
| 2026-08-02 | forward | 288 | 288 | 285 | 152 / 133 | 284 | 283 |

原样本门槛全部通过：训练 812（≥400）、校准 279（≥100）、三个检查日 285/281/285（均≥100），训练与校准均有两类标签。数量覆盖在训练及三个检查日均超过 50%，数量臂放行。逐日完整缺失原因保留于 `event_coverage_prelabel.json`；07-28 08 UTC 的弱覆盖小时仍在原分母中。报价缺失不以快照填洞，历史和数量缺失使用原 train-only 填充值及三臂共有标记。

## 冻结模型与三个检查日

训练只用 07-27/28/29；07-30 只选择 C∈{0.1,1,10}，不再 fit train+cal。R1/R2/R3 同一 offset-logistic/L2；样条、填充值和标准化仅由训练段决定。R0 是原 midpoint；R1 增加三自由度校准及共同质量控制，R2 再加 spread/30 秒变化，R3 再加 log(1+触价总量)/失衡。所有臂共享同一事件样本；主评分日等权、日内事件等权，epsilon=1e-6。

| 检查日 | N | R0 LL | R1 LL | R2 LL | R3 LL | R2−R3 gain |
|---|---:|---:|---:|---:|---:|---:|
| 2026-07-31 | 285 | 0.457682 | 0.466120 | 0.467013 | 0.466951 | +0.000062 |
| 2026-08-01 | 281 | 0.479620 | 0.473653 | 0.472678 | 0.478582 | -0.005905 |
| 2026-08-02 | 285 | 0.467894 | 0.467311 | 0.468556 | 0.480316 | -0.011760 |
| 日等权 | — | 0.468399 | 0.469028 | 0.469416 | 0.475283 | -0.005868 |
| 事件等权 | — | 0.468346 | 0.469006 | 0.469400 | 0.475268 | -0.005868 |

| 检查日 | R0 Brier | R1 Brier | R2 Brier | R3 Brier |
|---|---:|---:|---:|---:|
| 2026-07-31 | 0.153062 | 0.155879 | 0.156389 | 0.155939 |
| 2026-08-01 | 0.159321 | 0.157076 | 0.156899 | 0.159116 |
| 2026-08-02 | 0.153660 | 0.153425 | 0.154024 | 0.158774 |
| 日等权 | 0.155348 | 0.155460 | 0.155771 | 0.157943 |

07-30 所选 C：R1=0.1, R2=0.1, R3=0.1。所有候选的校准损失在 `model_results.json`。

四项原继续研究标准均未通过：gain 未达 +0.005、正向日期少于 2/3、Brier 恶化、R3 输给最佳简单基准 R0。

## 数量缺失、集中贡献和非交易尺度

| 检查日 | 数量完整 N / gain | 数量缺失 N / gain | 最大绝对单事件贡献 | 最大绝对 10 事件贡献之和 / 其余之和 | 中位数 abs(Δq) / spread |
|---|---:|---:|---:|---:|---:|
| 2026-07-31 | 285 / +0.000062 | 0 / undefined | +0.237817 | +0.635374 / -0.617753 | 0.7518 |
| 2026-08-01 | 281 / -0.005905 | 0 / undefined | -0.394987 | -1.219841 / -0.439392 | 2.3263 |
| 2026-08-02 | 284 / -0.011807 | 1 / +0.001604 | -0.527367 | -1.386678 / -1.965038 | 1.8843 |

集中贡献列是损失差的和，其余 gain 列为均值。极端预测的 min/p01/p99/max、每日期模型低于 bid/高于 ask 的比例，以及完整/缺失子集的 LL/Brier 均在聚合 JSON；逐事件贡献留在私有预测表。概率修正和 spread 的尺度比较没有识别成交选择、排队、取消延迟、费用或可实现收益。三个开发日不支持精确的长期置信结论。

## 资源、测试与复现

新增行情下载/扫描 **0 字节**，直接复用冻结小表；旧 112 GiB 提取阶段及其 **118729519345 字节**保守总账保留。新增查询资源和精确网络计数见 `settlement_closeout.json`；整批资源汇总见 `closeout_resources.json`。0 GPU，串行请求，本地 CPU 小表拟合，未打开 protected-final。

结算阶段实测 417.49 秒，评分 0.50 秒；二者合计 CPU 84.74 秒（0.023539 核时），峰值进程 RSS 142,868,480 字节。准备工作与测试 CPU 未单独计时；资源 JSON 区分实测量与以更早预算锚点计算的保守上界，不把它当作精确整机测量。

控制文件要求的 **13 项有限测试通过**：缓存恢复/预算/部分失败、RPC id/hex、方向与支付、Gamma 诊断，以及训练变换和检查日标签隔离。测试命令和代码哈希在 `closeout_tests.json`。公共隐私与 staged-diff 检查在交付前运行。

复现顺序：在私有原事件/缓存及固定日索引可读时，先运行 `scripts/verify_polymarket_multiday_ctf.py`（`--private-dir`、`--index-root`、`--public-dir`）；仅在 `settlement_closeout.json.status=COMPLETE` 且无未完成查询时运行 `scripts/fit_polymarket_multiday_price.py`。已有输出应先按哈希归档；恢复查询共用原持久账本。`resume_manifest.json`、`cache_migration.json`、`settlement_closeout.json` 和原 source receipts 绑定证据。没有改变日期、特征、模型、样本门槛或继续研究标准。

## 历史 112/96 GiB checkpoint（原文保留）

以下为当时停止状态；原未评分 JSON 已另存 `model_results_before_closeout.json`，当前结果以本报告顶部和新 `model_results.json` 为准。

# Polymarket BTC-5m 多日价格信息：112 GiB 续跑

**本批状态：`ACCESS_OR_BUDGET_BLOCKED`（2026-09-24 UTC）。** 固定 2026-07-27 至 2026-08-02 UTC 的七天、168 个小时和 2016 个 BTC 5-minute Up/Down 事件已完整提取，标签盲事件表已冻结。官方 CTF 身份查询已完成，结算查询因含重试的 **10,000 次逻辑请求上限**在最后 3023/6048 次 payout 调用之前停止。完整二元结算标签不可得，故预定训练/校准/三个检查日的**标签后样本门槛未能判断**；R0 未评分，R1–R3 未拟合，R3 对 R2 没有结果。没有以 Gamma 当前价格、成交情况或少数已结算事件替代固定完整样本。Quote-or-Pull A 继续为 **`STOP / DATA_GATED`**。

## 完整事件与标签盲覆盖

| UTC 日期 | 固定角色 | 确认事件 / 槽位 | 合格 `end−120s` 直接 BBO | 报价样本中有 30 秒历史 | 报价样本中合法触价快照 |
|---|---|---:|---:|---:|---:|
| 07-27 | train | 288 / 288 | 280 | 278 | 280 |
| 07-28 | train | 288 / 288 | 255 | 252 | 250 |
| 07-29 | train | 288 / 288 | 277 | 273 | 277 |
| 07-30 | calibration | 288 / 288 | 279 | 277 | 278 |
| 07-31 | forward development 1 | 288 / 288 | 285 | 283 | 285 |
| 08-01 | forward development 2 | 288 / 288 | 281 | 279 | 281 |
| 08-02 | forward development 3 | 288 / 288 | 285 | 283 | 284 |
| **总计** | | **2016 / 2016** | **1942** | **1925** | **1935** |

这七天从 Gamma 精确 slug、Up/Down token 顺序和计划结束时刻核验为 2016 个事件；行内 metadata 的 Up-token condition 冲突为 0。固定事件选择不使用成交、回报或赢家。07-28 08:00 UTC 的 12 个事件中，仅 1 个合格直接报价、0 个可用 30 秒历史和 2 个合法快照；该小时完整保留在训练分母。BBO 只取接收时间不晚于决策时刻、年龄 ≤1000 ms 的最新 `price_change.best_bid/best_ask`；快照独立取 ≤5000 ms 的完整 book，遇同接收时刻冲突或非法档位即标为缺失，不用旧有效记录回捞。逐日原因分布见 `results/polymarket_multiday_price_v1/event_coverage_prelabel.json`。

170 个清单内 CLOB 压缩对象的 168 个小时全部完成一次有效扫描，本轮实读 **104,945,544,485 字节**；每对象均核对清单大小并保留本次读取 SHA-256。首次扫描的解析错误修复导致已完成的 17 小时重扫，另为中断对象预留 1 GiB 保守字节；连同本轮实读，本批压缩源总上界 **118,729,519,345 字节**，低于授权 **112 GiB = 120,259,084,288 字节**，余 **1,529,564,943 字节**。源 ZIP SHA-256 `705c873ee9cd0f31fa455bc167dbf725218f69a03ae7fa933b19af3dbd710674`，清单 SHA-256 `db969fce2d2bf554743fbe486e6537066b826326771c4de48ec41f4b2019e109`。读取哈希是本次收据，不是供应商提供的独立上游哈希。`source_read_receipts.json`、`source_manifest_112gib.json` 和 `repair_1_manifest.json` / `repair_2_manifest.json` 保留具体来源及修复记录。

## 官方身份与结算预算停止

七个日索引可将 **1621/2016** 个事件的双 token 指向相应 condition；其余 **395** 个事件的 collection 与 position 查询已成功缓存。完整批次在无重试时需要 Gamma 2016、缺索引身份 1580、CTF payout 6048，合计 **9644** 次逻辑请求，距 10,000 上限仅 356 次。实际 RPC 响应触发大量重试。成功缓存的 CTF 调用为 collection 790、position 790、payout **3025/6048**；加 Gamma 为 **6621** 次成功缓存的逻辑调用。验证器在下一批 25 次 payout 发送前判定上限将被越过并退出。其内存计数据此位于 **9976–10000**；逐次重试账本未持久化，不能更精确声称已用数量。继续完成仍需 3023 次 payout，现有预算至多余 24 次，因此本批必须停止。详情见 `ctf_request_budget_stop.json`，所有 RPC 回复和 token/condition 行仍在私有目录。

**样本门槛与模型状态：** 1942 是结算前的报价覆盖，不是合格有标签样本。训练 ≥400、校准 ≥100、三个检查日各 ≥100、两类标签，以及数量臂在训练/检查样本的 ≥50% 合法快照门槛，均不能在缺失完整结算时正式判定。四臂及三个 forward 日均未运行，`model_results.json` 明确记录未拟合/未评分。本报告不提供 R3 相对 R2 的方向判断、置信区间或交易收益解释。

## 复现与边界

冻结配置、逐对象清单、标签盲提取、事件冻结、CTF 校验、预定 R0–R3 拟合代码及五个针对性测试在本科学分支。先前完整 96 GiB preflight stop 仍是有效历史结论；本次仅按新的 112 GiB 输入上限续跑相同七天。读取不涉及预留 final；原 07-28/29/30 08 UTC 旧诊断小时落在训练/校准段，三个后段日期仅是开发检查，不是独立 final。标签若将来补足，也只能称 `RETROSPECTIVE_OFFLINE`，因为历史规则版本和标签公开时刻未独立证明。没有运行 A 回放、撤单、markout、GRU、Transformer、tree、Sports、Weather 或 simulation。

## 历史 96 GiB preflight checkpoint（原文保留）

# Polymarket BTC-5m multiday price information: input budget stop

**Status: `ACCESS_OR_BUDGET_BLOCKED` (2026-09-24 UTC).** The frozen 2026-07-27 through 2026-08-02 UTC window cannot be extracted under the authorized 96 GiB compressed-source limit. The complete private source manifest lists **356 objects / 111,190,706,438 bytes**, exceeding **103,079,215,104 bytes** by **8,111,491,334 bytes**. The 168 canonical CLOB hourly objects alone total **104,620,375,984 bytes**, already **1,541,160,880 bytes** above the limit. No date, hour, variant, model, or threshold was removed to force a result.

| UTC day | Frozen role | CLOB objects / bytes | All listed objects / bytes |
|---|---|---:|---:|
| 07-27 | train | 24 / 16,589,467,438 | 50 / 17,431,944,919 |
| 07-28 | train | 25 / 15,870,661,995 | 53 / 16,778,686,730 |
| 07-29 | train | 24 / 17,127,430,555 | 50 / 18,079,996,705 |
| 07-30 | calibration | 24 / 15,559,547,314 | 50 / 16,427,958,811 |
| 07-31 | forward check 1 | 24 / 14,788,819,468 | 50 / 15,684,014,216 |
| 08-01 | forward check 2 | 25 / 12,837,401,708 | 53 / 13,771,711,853 |
| 08-02 | forward check 3 | 24 / 12,172,216,007 | 50 / 13,016,393,204 |

The remaining manifest objects are 172 on-chain objects / 6,073,991,705 bytes and 14 daily index objects / 171,170,248 bytes. The two noncanonical CLOB objects are included in the total. This is a **manifest count**, not proof of readable content, continuous capture, or an event roster. A local size-only check matched 12 of these 356 objects (three CLOB, three on-chain, six indexes; 1,718,042,410 bytes); Drive availability was not checked and is not inferred from this local count.

The stop occurred before market-object decompression or event extraction. Therefore confirmed events, Up-token identity, CTF settlement labels, end-minus-120-second BBO, 30-second history, and valid snapshot counts are **unknown**, not zero. The planned minimums (train ≥400, calibration ≥100, each of three checks ≥100; both train and calibration contain both labels) were not evaluated. R0 raw price, R1 calibrated price, R2 price/spread/move and the R3 snapshot-depth increment were **not fitted or scored**. There is no R3-versus-R2 finding and no evidence for or against continuing the quantity direction. No protected final data were opened. The existing Quote-or-Pull A decision remains **`STOP / DATA_GATED`**.

## Reproduction and limits

`results/polymarket_multiday_price_v1/preflight.json` records the frozen roles, per-day and per-kind counts, exact budget comparison, source ZIP SHA-256 `705c873ee9cd0f31fa455bc167dbf725218f69a03ae7fa933b19af3dbd710674`, and manifest SHA-256 `db969fce2d2bf554743fbe486e6537066b826326771c4de48ec41f4b2019e109`. The manifest was read from the existing private Rocklabs ZIP using `scripts/polymarket_multiday_price_preflight.py`; URLs never enter the public output. Two synthetic parser/budget tests passed. This batch read **zero CLOB/on-chain compressed objects**, made **zero official identity/settlement requests**, fitted **zero models**, and used **zero GPU**. Raw data, signed URLs, event-level prices/labels and predictions remain private. The manifest comes from the Rocklabs academic research source; path and size metadata do not certify content or upstream integrity.

The protocol's explicit response to this over-budget fixed window is to stop extraction and report the exact bytes. Any later study would require a separately authorized budget or source plan; this report does not release a final cohort or change A's gate.
