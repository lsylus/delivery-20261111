# B02 第四次修复当前交付报告

日期：2026-11-08

## 结论与范围

本轮仅修复 `docs/reviews/B02.md` 第三轮复审留下的 F01、F02、F04/F05、F06/F09 和 Windows 不稳定用例，不进入 B03/B04，不启动或代替新的独立复审。权威 Linux B02 runner 状态仍为 **blocked**：技术命令与 B01 当前源码依赖全部通过，真实 blocker 仅 `human-gate-0` 和由其产生的 `check-format-gate` blocked。

本轮没有运行 ODA 或任何真实 DWG 转换，没有操作真实 CAD，没有借用其他项目许可，没有人工批准声明，没有修改 `docs/reviews/B02.md` 或 `docs/orchestration/state.json`。第三次修复报告已按原字节归档为 `docs/reports/archive/B02-fix-3.md`，归档与替换前原文件 SHA-256 均为 `ff93587ef06802e420130d0cb0c18a2a657ca9d173f1a34eee66f2487df828af`。

## 第四次修复结果

| 发现 | 修复结果 | 验证 |
|---|---|---|
| F01 差异 PDF 跨格、源线段不可读 | 改为六列 candidate/source 表；源端点及全部 unmatched 源线段均进入 PDF；字号明确保持 5.5 pt，分页和行高由实际换行数计算 | 24 页、2,238 个单元格、34,163 个可见字形，0 次边界穿越；全页联系表及首/中/末页目检无裁切或重叠 |
| F02 PDF/CAD 字形与尺寸缓存超 0.1 mm | 可见 PDF 路径直接使用 ezdxf 的锁定字体 CAD glyph path；TEXT、MTEXT layout、MTEXT explode、透明检索层和独立测量都在仅含锁定 Noto 字体的隔离 font-manager 上下文中执行 | 每页 41 TEXT + 2 MTEXT，三页 876 个可见字形和 12 个尺寸箭头全部消费；最大文字/箭头边缘误差约 `0.000017 mm`，0 violation |
| F04/F05 有效显示属性、缓存同步位移、箭头比例和单页/合并不一致可漏检 | 回读从规划几何独立推导尺寸线原点、文字中点、缓存位置/方向/attachment、箭头位置/旋转/比例及 STYLE/TEXT 有效属性；probe 比较规范化后的单页/合并语义 | TEXT oblique 40、STYLE oblique 40、STYLE width 0.3、缓存 rotation 45、缓存与 midpoint 同步 x+20 mm、箭头 scale 0.1，6/6 拒绝；实际 probe 通过 |
| F06/F09 改名 Python、低熵垃圾 DWG 和自填命令记录可伪造 verified | Windows 要求有效 Open Design Alliance Authenticode 身份；Linux 在没有代码可信厂商签名/摘要时保持 unverified；capability 与 helper 共享 DWG 结构/熵校验；版本和转换命令必须绑定受控执行记录、executable hash/PID/argv/输入输出/日志 | 改名 Python 未执行且为 `available_unverified`；`AC1032`+重复字节垃圾因 low entropy 拒绝；required 分支 blocked；六场景 subprocess CLI 矩阵均得到预期状态 |
| Windows 时间戳变异可能未实际变化 | `changed_baseline_timestamp` 使用确定的一秒偏移，不再依赖紧邻 `datetime.now()` | Windows 最终完整回归 152 passed、0 skipped；第三轮复审首次 140 passed/1 failed 的历史事实保留，不改写历史证据 |

F03 长边引线/尺寸侧别、F07 构建与只读验证分离、F08 公共 C02 `DrawingPage` 继续保持有效。模板、fixture、历史证据、Batch 定义和已认可 B01 历史报告均未改动。

## F02 度量方法更正

第三轮复审使用 `MTextExplode` 独立测量缓存文字，但其临时样式没有在测量环境中注册锁定字体，可能落入系统字体 fallback。历史复审证据和结论保持原字节，不回写或覆盖。

本轮测量明确记录锁定字体绝对路径、SHA-256 `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`、family/PostScript identity，验证 `HEATER_CJK` 及两个 dimension cache 的样式，并逐 glyph 比较不透明 PDF Bezier 极值与使用同一受控 face 的 ezdxf TEXT/MTEXT 路径。该结果是修复方自检，仍请求下一轮独立复审核对方法与数值；不把方法更正写成独立认可。

## 实际执行结果

| 检查 | 权威结果 |
|---|---|
| Windows `tests/contracts tests/planning tests/formats` | 152 passed，0 skipped，90.65 s |
| Linux 同一完整回归 | 152 passed，0 skipped，48.50 s |
| 权威 DXF/PDF probe | exit 0；三页 readback、PDF/DXF 可见等价、单页/合并规范语义、candidate/template immutable 全部通过 |
| `tests/formats/test_probe_failures.py`（B02 runner） | 53 passed，0 skipped |
| 差异 PDF 独立检查 | 24 页；2,238 cells、34,163 visible glyphs、0 violation |
| 字形/尺寸独立检查 | 129 text entities、876 visible glyphs、12 arrows、0 violation；最大误差约 `0.000017 mm` |
| 负例 harness | 6/6 DXF mutation 拒绝；改名 Python、低熵 DWG、pending/required 分支均拒绝；`approval_claim: none` |
| subprocess CLI 矩阵 | 1 pytest passed；postpone/required-controlled 正分支通过，pending/矛盾状态/required-blocked/fake-verified 负分支按预期阻断 |
| 权威外部源码边界 | before/after 均 exit 0；`comparison.status=unchanged` |
| 权威 B01 runner | exit 0；53 contract + 46 planning，0 skipped；10 checks 全部 passed |
| 权威 B02 runner | exit 2 / blocked；probe、53 format、152 regression、dependency 和技术 checks 通过；仅 human gate 与 format gate blocked |
| 真实 DWG capability | `not_configured`、`conversion_run=false`、`approval_claim=none`；未调用 converter |

权威 Linux 源码提交为 `85aaa2c22ac079e479be07ca41076e7f736bd71f`；B01 绑定提交为 `fc39bc4c4046e43aadc6f317815c3ecaf60f21ea`。当前源码契约 SHA-256 为 `5017ac4fa7ced0bf6ddb45f1caec3ac02c4f6361cdde273bcef98ff05b98c781`。B01 impact report 绑定该源码提交和指纹；历史独立认可仍唯一指向 `B01-fix-2-r2/summary.json` 的 `fc1eaa3f...`，未被新 impact report 替代。

## CLI 状态矩阵

| 场景 | runner | gate | 结论 |
|---|---|---|---|
| `postpone_positive` | passed / 0 | passed | 延期合同自洽 |
| `pending_negative` | blocked / 2 | blocked | pending 不得通过 |
| `postpone_state_negative` | failed / 1 | passed | runner 拒绝延期却声称 DWG available |
| `required_blocked_negative` | failed / 1 | blocked | required 缺真实转换/CAD 证据时阻断 |
| `required_fake_verified_negative` | failed / 1 | blocked | fake verified 输出绑定不一致时阻断 |
| `required_controlled_positive` | passed / 0 | passed | 仅为临时 fixture 的分支可达性；不是转换、CAD 或批准证据 |

## 当前精确哈希

| 文件 | SHA-256 |
|---|---|
| `candidate/candidate-manifest.json` | `f9cb1dd279a1c95bfa9826e9f27910f7509ace48cca0959d244dcc1ee54aea4d` |
| `candidate/drawing-pages.json` | `a8e5aaae7bf501d90631f7676210643059662e2b5f7fb3027ae5f65b4cf1253c` |
| `candidate/heater-sample.dxf` | `b0c808911dd1b02cd03159b6016b5856763063c67ff1c31a10596bcf7fae9d8b` |
| `candidate/heater-sample.pdf` | `df89f6ca507a821acbbd6cf06cb55fdff82dfe5876fd20015a9d9f1518d3b852` |
| `candidate/reference-difference.pdf` | `7254d751ae1a423ad8ee830cfb4263fcff01af875b9c04513d96d3f109e52bed` |
| `validation/probe-result.json` | `7489fb83c0a8a655544a41d7f7b2ed33e01a784198b3da40b6784ed494c7cee6` |
| `visual-metrics.json` | `f1029408d586048d7c09f0727ef6bf9e2554c973c1c05a5fe0983fee19b70d28` |
| `difference-layout.json` | `8584dbfbd10256acb3cbee657f29c741ccf15f2a6480f7ccf6adf40886e6b5ca` |
| `negative-results.json` | `dccbe7f35d6c5dbe2d0827fa6fd65358742e772031def0cbbe84986de5ebb5cb` |
| `cli-state-matrix-results.json` | `ecb198fd605d9ab055802dde8962141e3943ef940341b7967db45ef4512b24fe` |
| `b01-runner/summary.json` | `f9f0860b928c66af526a34a6ae2e7f6d6da80c1ddff270dfb3a32150e9101cda` |
| `b01-acceptance.json` | `03a86a11ef586ab17d3941ca5695ab875a728b8c9c4bce08997c5a0636378620` |
| `b02-runner/summary.json` | `1e542bb30e1dbc5fca1e74b998be632c57b750c150cf6b6359f33903510b6c5d` |
| `human-approval.json` | `1661afc7cb09499df8b4d1f13deeb1b57dcbbcf82311d71b6d7e4c810b37e634` |
| `dwg/capability.json` | `d4de1c26eebbb1ef366ba31c0686a69fa1f1f2ac13c68284d0596ca8725c183e` |
| `gate-result.json` | `9d6cb0d0751f0b5c2ce9fc48aa3562a6916eb9734e184c80345b4adeb1f95bfd` |

除归档外，上表相对路径均位于 `docs/evidence/B02-fix-4/`。

## 未执行且不得宣称通过

- 未由具名工程师在真实 AutoCAD 2018 中打开精确冻结 DXF，编辑轮廓/文字/原生尺寸、显式更新尺寸、保存重开并提交绑定记录和截图。
- 未执行真实 DXF→DWG→DXF 正反转；未配置、调用或授权 ODA/其他 converter；没有真实 DWG 输出。
- 未获得模板重排、字体替代、逐线差异、5/10/10 mm 引线参数或 DWG 首发范围的人工批准。
- 未启动第四次修复后的独立复审；`docs/reviews/B02.md` 仍是第三轮历史 **FAIL**，本报告不能覆盖它。
- 未进入 B03/B04 或后续 Batch。

## 后续约束

1. 下一轮独立复审应只审阅 `B02-fix-4` 当前证据和源码指纹，并重新测量 F01/F02，特别核对受控 MTEXT 字体方法。
2. 在具名工程师完成精确候选的 AutoCAD 2018 编辑/保存/重开并批准模板、字体、引线与差异前，`human-gate-0` 保持 blocked。
3. 用户仍须对 DWG 首发范围作具名、带时间、绑定 candidate manifest 的决定。延期则保持 DXF/PDF 基线和 `conversion_run=false`；required 则必须提供本项目授权真实转换与目标 CAD DWG 证据。
4. 所有 `test_fixture_only` / `approval_claim: none` 正分支永远不得复制为生产、转换、CAD 或人工批准证据。
5. 上述门槛和独立复审完成前，B02 保持 blocked，不得标记 passed，也不得进入 B04。
