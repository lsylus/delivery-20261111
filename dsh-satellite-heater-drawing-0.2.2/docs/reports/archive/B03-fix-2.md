# B03 fix-2 实施报告

状态：**独立复审剩余 F01/F02 已修复；F03/F04/F05 防线保持通过。当前源码 B01 与最终 B03 runner 均 passed，等待同一独立审查聊天复验。** 本轮未进入 B04。

日期：2026-11-09（Asia/Shanghai）

## F01：超大有限 Decimal

- `exact_excel_numeric` 不再调用受 Decimal 上下文 `Emax` 影响的 `normalize()`。有效位数直接从 `as_tuple()` 计算，XLSX 数值指数边界在构造 Python `int` 前检查。
- `Decimal('1e1000000')` 及一百万个尾零的等价文本稳定产生 `UnsupportedExcelNumeric`，不再逸出 `decimal.Overflow`。这属于 XLSX 可表示性拒绝，不是新增工程量程。
- `validate_rows` 对真实三行工作簿形成 `resistance_ohm` 行级 `INVALID_FIELD`，保留源行 2/3/4、完整原值和修复建议，CLI exit 1、`outputs=[]`。
- 直接 writer 在创建目标目录前预检；新目录不创建，已有目标哨兵字节不变。既有 15 位精确值、冗余尾零、小/大精确值和真实案例仍写为 numeric cell 并无损往返。

## F02：共享字符串索引

- openpyxl 装载前解析 `[Content_Types].xml` 指定的 shared strings 与 worksheet parts。
- 每个实际 `t=s` 引用必须具有 `<v>`，使用非负十进制整数字面量，并小于实际 `<si>` 数量。比较不把任意长度索引转成 Python `int`，不会因超长索引引入新异常。
- `999999`、`-999999`、`-1`、非整数和缺失 `<v>` 均成为不可跳过 workbook `UNSUPPORTED_INPUT`；CLI 写完整 JSON、exit 1、`outputs=[]`，不生成 actual.xlsx，也不替换签署文字。
- 合法首索引 `0`、末索引 `44` 及合法前导零对照继续通过；末索引 O3 仍为 `CX-29-KR05-XM01`。`IndexError` 作为已知 openpyxl 损坏输入异常保留兜底，但负索引由预检主动拒绝，不依赖 catch。

## 保持关闭的边界

- F03：error/date/time 类型事实、公式拒绝和相同字面字符串正例全部保留。
- F04：limits 类型/有限性、256 字符边界、比例先长度后解析和 CLI `INVALID_REQUEST` 保留。
- F05：Windows 上标保留名、Unicode `Cc`、相邻安全代号保留。
- 原缺 shared strings、缺 workbook rels、损坏 DEFLATE、原 Decimal 精度/下溢/溢出反例均重新通过预期拒绝路径。

## 修改范围

- 实现：`service/src/heater_drawing/excel/numeric.py`、`service/src/heater_drawing/excel/reader.py`
- 回归：`tests/excel/test_b03_review_regressions.py`
- 当前绑定：`scripts/acceptance_registry.json`
- 报告与新证据：`docs/reports/archive/B03-fix-1.md`、`docs/reports/B03.md`、`docs/evidence/B03-fix-2/`

未修改 `docs/reviews/B03.md`、`docs/evidence/B03-review/`、`docs/evidence/B03-review-fix-1/`、旧失败输入、`docs/orchestration/`、CAD/格式、模板或其他业务模块。上一版实现报告已按原字节归档，SHA-256 为 `88e03700aaf2e0f500dfae26f83f0ef528c2f7b34c81709612096016d3553231`。

## 验证与证据

Linux 权威实现提交为 `b61da3af062f1d011f98ad26deb91fb69a3f3f74`；本地实现提交为 `19f4517acd33c8d1bb5533cdbbb8aaadc7d9cd5c`。两端为独立历史。

| 检查 | 结果 | 证据 |
|---|---:|---|
| Windows 受影响回归 | 209 passed | `tests/excel tests/contracts tests/planning` 终端实跑 |
| Linux 受影响回归 | 209 passed | 权威环境终端实跑 |
| fix-2 原文件/API/writer 核验 | 26/26 passed；原审查输入 hash 前后不变 | `docs/evidence/B03-fix-2/repair/results.json`，SHA-256 `e3208eb5ee68f797728a1f523935b30de13d7df121afaea8735118dbd6fd94c0` |
| 当前源码 B01 runner | passed；4/4 commands、10/10 checks、dirty_files=[] | `docs/evidence/B03-fix-2/b01-runner/summary.json`，SHA-256 `d0efa3ec374a3a6c41001f2e683bb594d5dcb0f52bd4c6a189689e4dd99bcaed` |
| 最终 B03 runner | passed；3/3 commands、3/3 checks、104 Excel tests、dirty_files=[] | `docs/evidence/B03-fix-2/b03-runner/summary.json`，SHA-256 `5b9ae6d70baaafe35dacd0dbf8719393d478971ceca163c27b0a850cb2e23b99` |
| B01 外部边界 | passed，comparison=unchanged | `b01-boundary-before.json` / `b01-boundary-after.json` |
| 真实案例 | valid，3 行，O3=郑玲，数量原文保留，actual 重读一致 | `repair/real-case.json` 与 `repair/real-case-actual.xlsx` |

最终 runner 源码指纹为 `aa7970bd99ec98531ed7935867f626165209f84b9b5e93a768bbfd565679ae64`。当前 B01 绑定 SHA-256 为 `ee3bf3f6cea224daf0d5300e1dfb5bdbbe670b71a279c74f616c9481315e5b08`。历史唯一接受摘要 `docs/evidence/B01-fix-2-r2/summary.json` 保持未改，SHA-256 仍为 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。

## 失败尝试与后续边界

本轮没有失败的实现、验证、绑定或同步尝试；结构化记录见 `docs/evidence/B03-fix-2/attempts.json`。

本轮只完成 B03 fix-2。比例放置、缺字/文字溢出、CAD/PDF、UI、跳过确认和任务流程仍属后续批次；不得据此声称图纸已可交付。后续仍须同时消费 parse 与 validation issues，任一 error 都不得绘图。完成后停手，等待同一独立审查聊天复验。
