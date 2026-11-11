# B02 第五次修复当前交付报告

日期：2026-11-08

## 结论与范围

本轮仅修复 `docs/reviews/B02.md` 第四轮独立复审留下的 F04/F05 和 F09，不进入 B03/B04，不启动或代替新的独立复审。第四轮已确认关闭的 F01、F02 保持关闭；本报告不再引用第三轮错误的 MTEXT fallback 度量。权威 Linux B02 runner 状态仍为 **blocked**：B01 当前源码依赖、DXF/PDF 技术证据及政策一致性检查全部通过，真实 blocker 仅 `human-gate-0` 和 `check-format-gate`。

本轮没有运行 ODA 或任何真实 DWG 转换，没有操作真实 CAD，没有借用其他项目许可，没有人工批准声明，没有修改 `docs/reviews/B02.md`、`docs/evidence/B02-rereview-4/` 或 orchestration 文件。第四次修复报告已按原字节归档为 `docs/reports/archive/B02-fix-4.md`；归档与替换前原文件 SHA-256 均为 `50b3ac27aa192f60ebd3ccfdffd7191521b004baa9408ae55cabb58c8ceafafc`。

## 第五次修复结果

| 发现 | 修复结果 | 实际验证 |
|---|---|---|
| F04/F05 尺寸缓存只覆盖部分属性 | 回读现在覆盖 LINE/ARC/CIRCLE/LWPOLYLINE、MTEXT 原文及格式、INSERT 变换和展开 SOLID 顶点；单页/合并语义签名纳入完整缓存，保留九位浮点归一 | 箭头块顶点、内联 MTEXT 宽度、缓存 LINE、缓存 LINE `+0.001 mm` 的完整 probe 均退出 1；`+3e-14 mm` 噪声按预期等价并退出 0 |
| 原生尺寸再次 `render()` 会移动文字/延伸线 | DIMSTYLE 显式锁定；`dimtad=0`、`dimexe=0`、`dimexo=0` 消除再生成漂移；独立 harness 对六个尺寸执行 render/save/reopen | 三页六尺寸全部通过；每项 7 个可见缓存实体的完整签名前后相同；锁定 Noto 字体和 DIMSTYLE 保存重开不变。该结果仅是 ezdxf 软件验证，不是 AutoCAD 验收 |
| PDF 黄色参考框可能渲染成黑色 | renderer 按受控 ACI 输出：ACI 2 黄色、ACI 7 黑色；probe 独立解析 PDF 描边颜色和端点 | 单页与合并 PDF 的黄色/黑色框线及坐标全部通过；黄色改黑的候选完整 probe 退出 1 |
| F09 自填或导入回执可冒充受控执行 | helper schema v2 绑定精确输入/输出字节、argv、executable、日志、PID、wall/monotonic 时间和记录摘要；只有同进程 runtime provenance 可建立执行事实 | 普通 Python DXF-copy helper 的同进程正例通过；导入同一记录保持 unverified；内部错误输入但外层自填正确、倒置时间和外部伪造记录均拒绝 |
| 高熵 `AC1032` 垃圾可被描述为结构有效 DWG | 无可信 DWG parser/readback 时一律 `structure_unverified`，不能升级为 verified capability | 高熵合成 DWG 字节被拒绝；真实 capability 保持 `not_configured`、`conversion_run=false`、`approval_claim=none` |
| runner 技术检查仍硬编码旧 `B02-fix-3` | `format-evidence` 从当前 registry 唯一 `check-format-gate --evidence` 推导证据根，并拒绝缺失、重复或越界路径 | 新回归把夹具移动到 `B02-fix-5` 后验证摘要只绑定注册目录；最终权威 B02 summary 的 inputs/artifacts 全部指向 fix-5，未出现 fix-3 |

F03 长边引线/尺寸侧别、F07 构建与只读验证分离、F08 公共 C02 `DrawingPage` 继续保持有效。第四轮独立复审对 F01/F02 的关闭结论没有被本轮重开；历史复审字节保持不变。

## 当前技术证据

- 冻结候选位于 `docs/evidence/B02-fix-5/candidate/`，包含三页可编辑 R2018 DXF、三份 A4 PDF/PNG、合并 DXF/PDF 和 24 页差异 PDF。
- DXF 回读验证 123 个可编辑 TEXT、6 个原生 DIMENSION、12 个 SOLID 箭头、完整尺寸缓存、精确 viewport、黄色参考框和受控字体。
- 可见度量覆盖 129 个文字实体、876 个可见字形和 12 个箭头；0 violation，最大边缘误差约 `0.000017 mm`。
- 差异 PDF 独立检查覆盖 24 页、2,238 个单元格和 34,163 个可见字形；0 violation。
- 完整 mutation harness 共 9 个案例：8 个可见语义错误按预期拒绝，`3e-14 mm` 归一噪声按预期接受。
- F09 组件 harness 明确标记 `test_fixture_only=true`、`converter_run=false`、`approval_claim=none`，不构成真实转换、DWG、CAD、许可或批准证据。

## 实际执行结果

| 检查 | 权威结果 |
|---|---|
| Windows `tests/contracts tests/planning tests/formats` | 162 passed，0 skipped，109.05 s |
| Linux 同一完整回归 | 162 passed，0 skipped，70.11 s |
| 权威 DXF/PDF probe | exit 0；三页 readback、完整缓存、黄色框、单页/合并语义、candidate/template immutable 全部通过 |
| `tests/formats/test_probe_failures.py` | 62 passed，0 skipped |
| 六尺寸再生成 harness | 6/6 passed；完整缓存签名相同；锁定字体和 DIMSTYLE 保存重开不变 |
| 全候选 mutation harness | `1,1,1,1,0,1,1,1,1`，与九个预期退出码完全一致 |
| 差异 PDF 检查 | 24 页；2,238 cells、34,163 visible glyphs、0 violation |
| 字形/箭头检查 | 129 text entities、876 visible glyphs、12 arrows、0 violation；最大误差约 `0.000017 mm` |
| F09 回执 harness | runtime DXF helper 正例通过；导入、伪造输入、倒置时间、高熵伪 DWG 全部拒绝 |
| subprocess CLI 矩阵 | 1 pytest passed；6 个测试夹具场景均得到预期状态 |
| 权威外部源码边界 | before/after 均 passed；`comparison.status=unchanged` |
| 权威 B01 runner | exit 0；53 contract + 47 planning，0 skipped；10 checks 全部 passed；`dirty_files=[]` |
| 权威 B02 runner | exit 2 / blocked；probe、62 format、162 regression、dependency 和三个技术 checks 通过；仅 human gate 与 format gate blocked；`dirty_files=[]` |
| 真实 DWG capability | exit 2；`not_configured`、`conversion_run=false`、`approval_claim=none`；未调用 converter |

权威 Linux 实现/候选提交为 `76b54248f39dc6b5603089c817e1d22b116c43ff`；runner 证据根修复提交为 `23e8aeb5ac5e054f97b71f5f7c000e66f05baa57`；B01 绑定提交为 `64c01fbec79f460caec2745ff0e54c07d937f13a`。当前源码契约 SHA-256 为 `d3fa48868141a1bf146b275d231c794637f6deaf884cff56f4f63ba9853c97e9`。历史独立认可仍唯一指向 `B01-fix-2-r2/summary.json` 的 `fc1eaa3f...`，未被新的 impact report 替代。

## CLI 状态矩阵

| 场景 | runner | gate | 结论 |
|---|---|---|---|
| `postpone_positive` | passed / 0 | passed | 延期合同自洽 |
| `pending_negative` | blocked / 2 | blocked | pending 不得通过 |
| `postpone_state_negative` | failed / 1 | passed | runner 拒绝延期却声称 DWG available |
| `required_blocked_negative` | failed / 1 | blocked | required 缺真实转换/CAD 证据时阻断 |
| `required_fake_verified_negative` | failed / 1 | blocked | fake verified 输出绑定不一致时阻断 |
| `required_controlled_positive` | passed / 0 | passed | 仅为 pytest 临时 fixture 的分支可达性；不是转换、CAD 或批准证据 |

## 当前精确哈希

除归档外，下表相对路径均位于 `docs/evidence/B02-fix-5/`。

| 文件 | SHA-256 |
|---|---|
| `candidate/candidate-manifest.json` | `fbc20a4ed55dda125af2d15ce9753d933ea80fe2d77ee190ba6293ac2f1f9064` |
| `candidate/drawing-pages.json` | `003807dba99a90f40fbe7b44905da476a5df58a38841f4ae4495d1ceb46a8243` |
| `candidate/heater-sample.dxf` | `7bc66cb55fb8ec845c01d5c0c2861f0ac4c903eff59100cc7b34fae5f246d5c4` |
| `candidate/heater-sample.pdf` | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| `candidate/reference-difference.pdf` | `4d9c2c4037397a1b1bf6ded15d8c8506906f1b16412f5733ca850262777a7a87` |
| `validation/probe-result.json` | `6b234482424345c4e92f588d1e8c848c10c2f72a21242c9e8009ec55bb6631ef` |
| `visual-metrics.json` | `f1029408d586048d7c09f0727ef6bf9e2554c973c1c05a5fe0983fee19b70d28` |
| `difference-layout.json` | `24ceea1b088834179ae47cae33318d5094f5abc9bd9900e64805c47b365fdda4` |
| `dimension-regeneration.json` | `8b379e3ef4be924cb5fc9449c6c2152add2f266ae9b966cac34d286f9de49cfb` |
| `full-probe-mutation-results.json` | `2ca250ac8878872ed3285a3267742d638d5be39999020bd9eaabb106ff2801c0` |
| `dwg-receipt-results.json` | `12456d3ac8fec2f5bc5cc35dcc4c29813e7079e4de16f04e578a9fd1c19eb2c5` |
| `cli-state-matrix-results.json` | `ecb198fd605d9ab055802dde8962141e3943ef940341b7967db45ef4512b24fe` |
| `b01-runner/summary.json` | `3b60fe34dca5c4b068791d7307ec7c832431aebdc68e71430c88fcd5cb9f94f3` |
| `b01-acceptance.json` | `df0235638e7eb9471bf075d6158dbd67de355be4fb7b64ed6937febfbca58eba` |
| `b02-runner/summary.json` | `221ba108c359a6d82f16ecba2f3659eacdcacd4ad268048bfc7941c3856f35c9` |
| `human-approval.json` | `57f9ebcee179ad067bb31a9d774c262f7de0534d41b3bda410659679cd21a7c3` |
| `dwg/capability.json` | `938e0d4637e7a9ba820f2975c1bd50e16c29db19873751d72b9be3382ec2974f` |
| `gate-result.json` | `fc9d73b7a0681a0072cf6320acaec8eb965e3473c8af5fa7b024343530709150` |
| `docs/reports/archive/B02-fix-4.md` | `50b3ac27aa192f60ebd3ccfdffd7191521b004baa9408ae55cabb58c8ceafafc` |

## 未执行且不得宣称通过

- 未由具名工程师在真实 AutoCAD 2018 中打开精确冻结 DXF，编辑轮廓/文字/原生尺寸、显式更新尺寸、保存重开并提交绑定记录和截图。
- 未执行真实 DXF→DWG→DXF 正反转；未配置、调用或授权 ODA/其他 converter；没有真实 DWG 输出。
- 未获得模板重排、黄色图框、字体替代、逐线差异、5/10/10 mm 引线参数、尺寸再生成行为或 DWG 首发范围的人工批准。
- 未启动第五次修复后的独立复审；`docs/reviews/B02.md` 仍是第四轮历史 **FAIL**，本报告不能覆盖它。
- 未进入 B03/B04 或后续 Batch。

## 后续约束

1. 下一轮独立复审只审阅 `B02-fix-5` 当前证据和源码指纹，重点复核完整缓存变异、六尺寸再生成、黄色框和 F09 回执/结构状态。
2. 在具名工程师完成精确候选的 AutoCAD 2018 编辑/更新尺寸/保存/重开并批准模板、字体、颜色、引线与差异前，`human-gate-0` 保持 blocked。
3. 用户仍须对 DWG 首发范围作具名、带时间、绑定 candidate manifest 的决定。延期则保持 DXF/PDF 基线和 `conversion_run=false`；required 则必须提供本项目授权真实转换与目标 CAD DWG 证据。
4. 所有 `test_fixture_only` / `approval_claim: none` 正分支永远不得复制为生产、转换、CAD 或人工批准证据。
5. 上述门槛和独立复审完成前，B02 保持 blocked，不得标记 passed，也不得进入 B04。
