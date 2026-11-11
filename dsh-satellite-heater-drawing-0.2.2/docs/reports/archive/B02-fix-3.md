# B02 第三次修复当前交付报告

日期：2026-11-07

## 结论与范围

本轮仅完成 B02 第三次修复，不进入后续 Batch，不启动新的独立审查。当前技术实现、B01 当前源码依赖绑定、DXF/PDF 候选、格式探针、DWG 状态策略与正反分支测试均已完成；权威 B02 runner 状态仍为 **blocked**，真实 blocker 只有 `human-gate-0` 和 `check-format-gate`。

本轮没有运行 ODA 或任何真实 DWG 转换，没有借用其他项目许可，没有伪造人工批准，没有修改 `docs/reviews/B02.md`，也没有修改本地或远端的 `docs/orchestration/state.json`。第二次修复报告已按原字节归档为 `docs/reports/archive/B02-fix-2.md`，归档 SHA-256 与原文件均为 `2aa8796426f696cbe44ce3b8faf958fcde2eed22c24a427f62ba63213ea2ef76`。

## 第三次修复发现与处理

| 发现 | 第三次修复结果 | 当前证据/边界 |
|---|---|---|
| 字体选择仍可能漂移，PDF 可见文字与 CAD 度量没有完全同源 | 字体解析锁定 Noto Sans CJK SC face 与 SHA-256；CAD 文本度量使用该字体真实轮廓和规范放置；PDF 可见文字直接绘制同一字体 outline，并保留透明可搜索文字 | `validation/probe-result.json` 的 `glyph_coverage`、逐文字 bbox、PDF embedded font 与 4 倍像素等价结果 |
| 原生尺寸只检查显示值，未充分绑定 DIMSTYLE、字体和缓存 | 严格回读 `STYLE` 文件名、字体身份/hash/license/coverage、`HEATER_DIM` 关联、dimension cache 文本/位置/高度；尺寸、文字与 viewport 变异均有反例 | `tests/formats/test_probe_failures.py`；B02 `format-failure-tests` 为 42 passed |
| PDF 只靠文本/结构可能漏掉可见几何差异 | 每页与合并 PDF 都生成规范临时 PDF，在 4 倍分辨率比较实际可见像素；三页 `changed_channels=0` | `validation/probe-result.json` 的 `visible_dxf_equivalence` 与 `merged_page_equivalence` |
| 参考图差异匹配可能按顺序误配，差异表长字段曾溢出 | 改为三页一对一线段匹配，综合方向、长度、端点、重叠，并显式报告 unmatched/relayout/text-unknown；修复 `field-standards_reviewer` 表格布局 | `candidate/reference-measurements.json` 与 11 页 `candidate/reference-difference.pdf`；已逐页目视复核 |
| DWG helper 可被任意 Python/header padding 冒充，语义签名不完整 | 只接受本项目授权的原生 ODA executable 身份、版本回执、固定 argv、非空日志、具名操作者/时间；完整语义签名覆盖坐标、样式、尺寸/缓存、布局和 viewport | `dwg_adapter.py` 与 DWG 回归反例；真实 `dwg/capability.json` 仍为 `not_configured`、`conversion_run=false` |
| required-DWG gate 可与 converter 输出或目标 CAD 记录脱节 | required 分支必须绑定精确 verified converter DWG，再绑定独立 AutoCAD 2018 操作者、时间、动作、输入/输出、结构化记录及截图 | `check_format_gate.py`；完整 CLI 矩阵的 required-blocked/fake/controlled 分支 |
| B02 可消费被裁剪或替换的 B01 当前源码摘要 | 新 `b01-acceptance.json` 绑定精确 summary hash/source fingerprint/head、registry 命令合同、必需 checks 顺序、完整 input/artifact 集、两份边界输入和历史已接受 B01 事实；绑定必须与当前 Git HEAD blob 一致 | B01 裁剪/argv/绑定 mutation 反例全部被真实 `verify_batch.run_batch()` 拒绝 |
| 原 11 项状态矩阵的执行层级表述不清 | 如实区分两层：原 11 项导入真实 `verify_batch.py` 后直接调用 `run_batch()`，通过 monkeypatch 临时 ROOT/registry，不执行 gate CLI；本轮新增完整 subprocess CLI 矩阵，直接执行复制到临时项目的真实 `check_format_gate.py` 与 `verify_batch.py` | `state-matrix/pytest.xml` 与 `cli-state-matrix/results.json`，两者均标明 test fixture，不构成人工批准 |

F03 长边引线与原生尺寸冲突、F07 构建/只读验证、F08 公共 C02 `DrawingPage` 继续保持关闭，没有回退。

## 新方案与可信边界

1. **DXF/PDF 核心基线**：三页 R2018 DXF、A4 PDF/PNG、合并 PDF 与 `DrawingPage` 来自同一冻结候选；模板、字体、尺寸与 PDF 可见输出由同一读回/像素证据约束。
2. **DWG 是显式升级，不是默认产物**：真实状态仍为 `pending_user_decision`。延期时必须保持 `conversion_run=false` 和 blocked capability；若要求首版 DWG，则真实转换、正反转、语义等价与目标 CAD DWG 编辑保存重开全部成为硬门槛。
3. **B01 当前源码依赖**：历史已接受事实继续锁定 `docs/evidence/B01-fix-2-r2/summary.json` 的 SHA-256 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`；本轮另以 current-source contract 验证最终源码影响，不把新 impact summary 冒充既有独立复审批准。
4. **源码边界**：最终源码契约指纹为 `08791e96eb0e9143646edf2428526fa6b8ddd632dede9c4091c73706427a999a`。权威 Linux 的 before/after 边界均绑定该指纹，外部参考比较为 `unchanged`。
5. **测试 fixture 边界**：完整 CLI required 正分支使用 pytest 临时目录中的受控 DXF、带 `AC1032` 头的测试字节、结构化记录与临时身份，只证明 gate/runner 分支可达和合同自洽；`results.json` 明确写入 `approval_claim: none`，不得引用为真实 CAD、真实 converter 或人工批准。

## 实际执行的检查

| 命令/检查 | 实际结果 |
|---|---|
| 权威环境同步 | Python 3.12.16、PyMuPDF 1.28.2、ezdxf 1.4.5、fontTools 4.68.0；`service/uv.lock` SHA-256 `7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60` |
| 构建 `B02-fix-3/candidate` | exit 0；三页 DXF/PDF/PNG、合并 PDF、DrawingPage、逐线差异报告生成成功 |
| 权威只读 DXF/PDF probe | exit 0；三页语义、字体、原生尺寸、单页/合并可见像素等价、candidate immutable 全部通过 |
| `tests/formats/test_probe_failures.py` | 42 passed，0 skipped |
| `tests/contracts tests/planning tests/formats`（权威 B02 runner） | 141 passed，0 skipped |
| 原函数级 state matrix | 11 passed；6 个 DWG 状态 + 5 个 B01 mutation；调用真实 `run_batch()`，但 ROOT/registry 被 monkeypatch，未调用 gate CLI |
| 完整 CLI state matrix | 1 个 pytest 内执行 6 个 subprocess 场景；pytest passed；逐场景结果见下表 |
| 权威 B01 runner | exit 0；53 contract + 46 planning，0 skipped；10 个 B01 checks 全部 passed |
| 权威 B02 runner | exit 2；B01 dependency、DXF/PDF 技术证据、DWG pending 策略、format-gate record 均 passed；仅 human gate 与 format gate blocked |
| 真实 DWG capability probe | exit 2；`status=blocked`、`conversion_run=false`、converter/license/verified output 均为空 |
| 真实 format gate | exit 2；模板/字体/引线/目标 CAD 批准 pending，DWG 范围决定 pending |
| Windows 最终完整回归 | 141 passed，0 skipped |
| 视觉检查 | 三张权威 PNG 与 11 页差异 PDF 均无裁切、遮挡或表格溢出 |

### 完整 CLI 分支矩阵

| 场景 | `verify_batch.py` | runner 状态 | gate 状态 | 结论 |
|---|---:|---|---|---|
| `postpone_positive` | 0 | passed | passed | 延期记录、blocked/unrun DWG 状态与 gate 合同一致 |
| `pending_negative` | 2 | blocked | blocked | 明确拒绝把 pending 决定当通过 |
| `postpone_state_negative` | 1 | failed | passed | gate 单独可通过，但 runner 拒绝“延期却声称 DWG available”的矛盾状态 |
| `required_blocked_negative` | 1 | failed | blocked | DWG required 时，不可用 capability 和缺失 DWG CAD 记录被拒绝 |
| `required_fake_verified_negative` | 1 | failed | blocked | verified converter 输出与目标 CAD 输入不一致时被拒绝 |
| `required_controlled_positive` | 0 | passed | passed | 仅证明完整 required 分支在临时测试合同下可达；不构成批准或真实转换 |

## 未执行且不得宣称通过的检查

- 未由具名工程师在真实 AutoCAD 2018 中打开本轮精确冻结 DXF，编辑轮廓/文字/原生尺寸、显式更新尺寸、保存重开并提交输入/输出 hash、结构化记录和截图。
- 未执行任何真实 DXF→DWG→DXF 正反转；未配置、调用或授权 ODA/其他 DWG converter；未验证真实 converter 版本、日志和 ACAD2018 DWG。
- 未获得模板重排、Noto SC 字体替代、逐线差异、5/10/10 mm 引线参数或 DWG 范围的人工批准。
- 未启动第三次修复后的独立复审；`docs/reviews/B02.md` 保持既有 FAIL 历史，不被本报告覆盖。
- 未进入 B03/B04 或任何后续 Batch；未运行服务部署、DSH Host/MCP、浏览器、真实工程端到端或生产安装检查。

## 当前精确哈希

| 文件 | SHA-256 |
|---|---|
| `docs/evidence/B02-fix-3/candidate/candidate-manifest.json` | `ede33aba47e52fd101826fec473f5af8b953389e52856e82d5de13ce5158af4b` |
| `docs/evidence/B02-fix-3/candidate/drawing-pages.json` | `676f98c07e7687478bec48e851fe58590e001732ea01435c725242c2fdc58739` |
| `docs/evidence/B02-fix-3/candidate/heater-sample.dxf` | `5984555dd8da5bdec572e3cd9b9fcd8de29e6df38d6c94b37c364ef6d32eceea` |
| `docs/evidence/B02-fix-3/candidate/heater-sample.pdf` | `2590306e3da7f483fef051d7865cdfc0d25f069e601c90a63d1fa934c19367b5` |
| `docs/evidence/B02-fix-3/candidate/reference-difference.pdf` | `bc8b3abfbc9757ca023c5fadfe4f68036fd4aae903c645a0124b728fd5a0b2b3` |
| `docs/evidence/B02-fix-3/validation/probe-result.json` | `77f93d34fb8af5026c0315dcdde42f724cae397fcc4c7c41e0919752a3315cbc` |
| `docs/evidence/B02-fix-3/b01-acceptance.json` | `bf4ba720c57d82970e4d5869760940dafc1f144f11e651e4c779faf9063b15d2` |
| `docs/evidence/B02-fix-3/b01-runner/summary.json` | `1d01759cc4d2e471b42e88780c42badacbf33bc3fffb1e28c0db3efee7821181` |
| `docs/evidence/B02-fix-3/b02-runner/summary.json` | `d24f7725ea01c930f3fa646b619da2c9d1be74e132cb110d4211c17b4d7c5ac9` |
| `docs/evidence/B02-fix-3/state-matrix/pytest.xml` | `2d9094b072d8ccbce8f14bb972489b5456cc51500c3f02f9b904201d4719b0f3` |
| `docs/evidence/B02-fix-3/cli-state-matrix/results.json` | `ecb198fd605d9ab055802dde8962141e3943ef940341b7967db45ef4512b24fe` |
| `docs/evidence/B02-fix-3/cli-state-matrix/pytest.xml` | `77fa63c23dc95bc04d57b3e2bb3e331096d0404532bfa67181ac41c3182b439a` |

## 用户可审阅文件

- 当前报告：`docs/reports/B02.md`
- 第二次修复原字节归档：`docs/reports/archive/B02-fix-2.md`
- 当前进度：`docs/progress.md`
- 权威候选清单与三页汇总：`docs/evidence/B02-fix-3/candidate/candidate-manifest.json`、`heater-sample.dxf`、`heater-sample.pdf`
- 三张可视渲染：`docs/evidence/B02-fix-3/candidate/renders/`
- 逐线差异：`docs/evidence/B02-fix-3/candidate/reference-measurements.json`、`reference-difference.pdf`
- 权威探针与 runner：`docs/evidence/B02-fix-3/validation/probe-result.json`、`b01-runner/summary.json`、`b02-runner/summary.json`
- B01 当前源码绑定：`docs/evidence/B02-fix-3/b01-acceptance.json`
- 两层状态矩阵：`docs/evidence/B02-fix-3/state-matrix/pytest.xml`、`cli-state-matrix/results.json`
- 真实 pending 记录：`docs/evidence/B02-fix-3/human-approval.json`、`dwg/capability.json`、`gate-result.json`

## 后续约束与剩余真实门槛

1. 在具名工程师完成精确候选的 AutoCAD 2018 编辑/保存/重开并批准模板、字体、引线与差异前，`human-gate-0` 不得改为 passed。
2. 用户必须对 DWG 首版范围作具名、带时间、绑定 candidate manifest 的决定。若延期，保持 DXF/PDF 基线和 `conversion_run=false`；若 required，必须提供本项目授权真实 converter 正反转及目标 CAD DWG 证据。
3. 临时测试中的 `required_controlled_positive` 永远不得复制为生产/人工证据，也不得用于改变真实 `human-approval.json`、`dwg/capability.json` 或 `format-profile.json`。
4. 新的独立复审只能审阅本报告列出的 `B02-fix-3` 当前证据和源码指纹；不得复用 `B02-fix-2` 结论。修复与双端 clean 全部完成前不启动审查。
5. 以上门槛完成并经独立复审前，B02 保持 blocked，不得标记 passed，也不得进入 B04。
