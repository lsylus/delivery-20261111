# B02 第二次修复交付报告

日期：2026-11-07

## 结论

本轮仅执行 B02 第二次修复。技术候选、严格回读、PDF 语义探针、DWG 证据状态机和延期 runner 路径已修复并通过测试；B02 总状态仍为 **blocked**。`docs/reviews/B02.md` 的独立复审结论继续是 **FAIL**，直到新的独立复审完成。本轮未进入后续 Batch，未运行 ODA 或真实 DWG 转换，未复用其他项目许可，未改评审文件或任何 `docs/orchestration/state.json`。

冻结证据位于 `docs/evidence/B02-fix-2/`。汇总 DXF SHA-256 为 `9b893f26...f80f4`，汇总 PDF 为 `df1b40d5...52bd`，candidate manifest 为 `67b9672e...567b3`，最终源码契约指纹为 `9424d896...03de`。

## 修复结果

| 项目 | 本轮结果 | 证据 |
|---|---|---|
| F01/F02 字体度量、越界与差异 | CAD/PDF 共用锁定 SC 面的 `unitsPerEm=1000`、`sCapHeight=733` 与真实轮廓；三页文字均在纸面/受控单元格内，无文字/图框及文字/文字相交 | `validation/probe-result.json` 的逐文字 bbox；三张 PNG；`reference-measurements.json` 与两页差异 PDF |
| F04 尺寸字体 | `HEATER_DIM.dimtxsty=HEATER_CJK`；每个原生 DIMENSION 的 virtual MTEXT 均严格回读该样式 | 6 个 DIMENSION、12 个 SOLID 箭头与 mutation tests |
| F05 严格回读/PDF | 拒绝 `dimlfac=10`、viewport twist、A3 宽度、错误对齐、删除图框及历史反例；单页 PDF 验证页数、A4、完整文本、矢量流、零栅格，合并 PDF 验证页序 | 36 项格式失败用例，0 skipped |
| F06 CAD gate/DWG 延期 | CAD 记录绑定精确输入、具名人员/时间、完整动作、独立输出、结构化记录和真实 PNG/PDF 头；拒绝未来决定和无关 fixture；DWG probe 改为非必需政策事实 | 合成正反分支仅在临时测试目录运行；真实 gate 仍 pending |
| F09 DWG 真实性/helper | 只有已识别产品/版本、精确 executable/hash、双向 argv、完整 stdout/stderr、实质 AC1032 DWG、可审计 DXF 与相同语义签名才升级；失败/超时日志持久化 | 假 DXF/任意 Python 保持 unverified；垃圾、header-only、stale、非零、timeout 均拒绝 |

F03 长边引线/尺寸原冲突、F07 构建与只读验证、F08 公共 C02 `DrawingPage` 保持关闭，没有回退。

## 验证

| 命令/检查 | 结果 |
|---|---|
| 构建最终 `B02-fix-2/candidate` | exit 0；三页 DXF/PDF/PNG、合并文件、DrawingPage、逐线差异证据 |
| 只读 DXF/PDF probe | exit 0；candidate/template immutable；三页语义通过 |
| `tests/formats/test_probe_failures.py` | 36 passed，0 skipped |
| `tests/contracts tests/planning tests/formats` | 123 passed，0 skipped |
| DWG capability probe | exit 2；`conversion_run=false`、`status=blocked`，未调用转换器 |
| format gate | exit 2；仅真实 CAD/human 批准和 DWG 范围决定待定 |
| 默认 B01 runner | exit 0；新 before/after 边界与最终源码指纹匹配 |
| 默认 B02 runner | exit 2；当前 B01 dependency passed，三个技术命令通过，非必需 DWG probe blocked；实际 blockers 仅 human gate 和 format gate |

历史 `B01-fix-2-r2/summary.json` 及其认可 hash 保持不变。默认 B02 dependency 通过 `current_source_contract` 模式消费本轮真实通过的 `b01-runner/summary.json`，并逐一复核命令日志、输入、产物、状态与时效，避免 registry 嵌入当前 summary hash 造成指纹自引用。新的 B01 impact summary 尚待独立复核，但已正确消除陈旧依赖技术 blocker。

Blocker 分类：技术实现与依赖证据链无 blocker；`probe-dwg-candidate` 是非必需环境事实，不进入 blocker；人工/政策 blocker 为 `human-gate-0` 和 `check-format-gate`；独立复审状态仍为 FAIL，需新一轮复核。

## 仍需真实人员完成

- 具名工程师在 AutoCAD 2018 打开确切冻结 DXF，编辑轮廓、文字和原生尺寸，显式更新尺寸，保存重开，并提交输入/输出 hash、结构化记录及截图。
- 审批模板重排、SC 字体替代、逐线差异和 5/10/10 mm 引线参数。
- 对最终新证据做独立复审；当前 `docs/reviews/B02.md` 不被本报告覆盖。
- 用户决定首版延期 DWG 或要求 DWG。若要求首版 DWG，必须另有本项目授权真实正反转与目标 CAD DWG 编辑保存重开证据。

在以上门槛完成前，B02 不得标记 passed，也不得进入 B04。
