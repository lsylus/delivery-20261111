# B03 fix-3 实施报告

状态：**F02 剩余 P1 已修复；F01 与 F03–F05 防线保持通过。当前源码 B01 与最终 B03 runner 均 passed，等待同一独立审查聊天复验。** 本轮未进入 B04。

日期：2026-11-09（Asia/Shanghai）

## F02：按实际消费路径预检共享字符串

- 预检从 `xl/workbook.xml` 读取 sheet `r:id`，通过 `xl/_rels/workbook.xml.rels` 解析 openpyxl 实际消费的工作表部件，不再只枚举 `[Content_Types].xml` 的 worksheet Override。
- OPC relationship 目标同时支持相对路径和有效的绝对等价路径；规范化后仍使用已有安全部件名检查，拒绝越界或非 OPC 目标。
- 共享字符串表按有效内容类型与 workbook relationship 一致解析。内容类型按 Override 优先、Default 按扩展名回退；多表或关系不一致明确拒绝。
- 每个实际消费的 `t="s"` 单元格仍必须有 `<v>`，必须是 ASCII 非负整数，且必须小于实际 `<si>` 数量。`IndexError` 保留为 loader 损坏兜底，负索引由预检主动拒绝。

独立复现的 Default worksheet `O3=-1` 现在返回不可跳过 workbook `UNSUPPORTED_INPUT`，CLI exit 1、完整 JSON、`outputs=[]`，不写 actual.xlsx。同包布局下 `O3=0` 仍 valid，值为 `阻值偏差(Ω)`。

## 回归与边界

- 新增 7 个回归：审查 Default 负/正对照，Default/Override 优先级，改名工作表，相对/绝对 relationship 目标的负索引与合法索引。
- 原 `-1`、正/负越界、非整数、缺失 `<v>` 仍拒绝；`0`、末索引、合法前导零、普通工作簿和 actual 往返仍通过。
- F01 超大有限 Decimal 仍稳定形成行级 `INVALID_FIELD` 或 `UnsupportedExcelNumeric`，writer 无目标副作用。
- F03 error/date 类型、F04 非有限 limit、F05 保留名和控制字符防线保持通过。

## 修改范围

- 实现：`service/src/heater_drawing/excel/reader.py`
- 回归：`tests/excel/test_b03_review_regressions.py`
- 当前绑定：`scripts/acceptance_registry.json`
- 报告与新证据：`docs/reports/archive/B03-fix-2.md`、`docs/reports/B03.md`、`docs/evidence/B03-fix-3/`

未修改 `docs/reviews/B03.md`、`docs/evidence/B03-review/`、`docs/evidence/B03-review-fix-1/`、`docs/evidence/B03-review-fix-2/`、原失败输入、`docs/orchestration/`、CAD/格式、模板或其他业务模块。fix-2 实施报告已按原字节归档，SHA-256 为 `d3583768fa050c42516aeb909fb8b724ed697c61105e0c964b6d58e736b566fb`。

## 验证与证据

| 检查 | 结果 | 证据 |
|---|---:|---|
| Windows 受影响回归 | 216 passed | `tests/excel tests/contracts tests/planning` 终端实跑 |
| Linux 受影响回归 | 216 passed；wheel 重建成功 | 权威环境终端实跑 |
| fix-3 定向核验 | 25/25 passed；777 个受保护文件哈希不变 | `docs/evidence/B03-fix-3/repair/results.json`，SHA-256 `5d9d58736012597580a89a9c30fdff132a509fdedf3bb7df8e49a1b1dc45bb06` |
| 当前源码 B01 runner | passed；4/4 commands、10/10 checks、`dirty_files=[]` | `docs/evidence/B03-fix-3/b01-runner/summary.json`，SHA-256 `4060cc82e9ba647c45060e833a44b3a211e7e42aa38c2a0fb4b224b0a873bcab` |
| 最终 B03 runner | passed；3/3 commands、3/3 checks、111 Excel tests、`dirty_files=[]` | `docs/evidence/B03-fix-3/b03-runner/summary.json`，SHA-256 `32f1eaf493c3976fcb45225029f2d609ec727963ee18a4e5397a1e2fb8f0f053` |
| B01 外部边界 | passed，comparison=`unchanged` | `b01-boundary-before.json` / `b01-boundary-after.json` |
| 真实案例 | valid，3 行，O3=`郑玲`，actual 重读一致 | `repair/real-case.json` 与 `repair/real-case-actual.xlsx` |

最终 runner 源码指纹为 `34cc7b2841915db9c2cf53a606ada702f48191173742fe7530cedce82a5b88d4`。当前 B01 绑定 SHA-256 为 `77f650685814186a1d2f61dec46285096c65774c8c93044d37128d9b15e5499c`。历史唯一接受摘要 `docs/evidence/B01-fix-2-r2/summary.json` 保持未改，SHA-256 仍为 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。原工作簿 SHA-256 仍为 `25e06f4ce14b366fe6f4ca89af7ccda1f707af62a6aded16a87be7028417e4e5`。

Linux 权威实现提交为 `8c5f5c1b96c0eda099dbb295b30240843f385b4a`；本地实现提交为 `d7da17511785464a5da9d125520db42ea3aaedbf`。两端为独立历史。

## 失败尝试与后续边界

B01 绑定命令成功后，一条仅用于展示 summary 字段的远端 Python 命令因 shell 引号错误产生 `SyntaxError`；改用 `jq` 读取后核对 passed。首条残留 pytest 进程过滤命令也因 `awk` 转义错误未执行；改用锚定 Python 命令行的 `pgrep` 与本地进程查询后确认两端无 pytest。两次失败的只读展示/过滤命令均未改动源码或证据。结构化记录见 `docs/evidence/B03-fix-3/attempts.json`。

本轮只完成 B03 fix-3。比例放置、缺字/文字溢出、CAD/PDF、UI、跳过确认和任务流程仍属后续批次；不得据此声称图纸已可交付。后续仍须同时消费 parse 与 validation 全部 issues，任一 error 都不得绘图。完成后停手，等待同一独立审查聊天复验。
