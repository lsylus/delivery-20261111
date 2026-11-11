# B02 第八轮修复独立复审

结论：**FAIL。第七轮 Continuous 实际定义漏洞已关闭；本轮发现当前原生尺寸再生成来源仍漏检线型引用（P1），以及待签材料与最终模板/机器门槛不同步（P2）。技术闭环未完成，不能标“技术闭环可送人工”。** 正常冻结候选及默认 runner 的技术检查通过，不抵消独立完整反例的错误接受；真实目标 CAD、具名工程审批及 DWG 范围决定仍未完成。

仅写本报告、第七轮原字节归档 `docs/reviews/B02-rereview-7.md`、新证据 `docs/evidence/B02-rereview-8/`。归档 SHA-256：`114e7562ba70c361773798ba68be63d18076735a420b1d11572b49e35acf46f3`。业务、测试、执行报告、冻结候选、决定、registry、模板及各自 orchestration 均未改。未启动 B03、新聊天或子代理；未运行 ODA、真实 converter、真实 DWG 转换或目标 CAD，未借许可、未代签。

## 身份、材料与独立执行范围

用户交接本地 `7d4cc7fd9d243db9fbf659d1277ee2a8be791928`，实际开始为仅追加调度文档的 `a4c57b8d882104b091d202952dae13d52aeac217`；远端 `5169a5e859133354213cd74eab537e6ab0f361bd`。两端初始均 clean、分支 `codex/b01-foundation`。未发现适用祖先或子目录 AGENTS。源码契约一致：**`ae71328789ba590b5c681a4d376f56e8ed571ef1538182e227080a74e1ae4a7f`**，不以纯文档 HEAD 差异判源漂移。

已读 plan、B02、当前执行报告、上轮复审、C02/C05/C06/C07、R02–R04/R07、project-baseline、progress、B01 报告与当前决定。实际阅读两端 focused diff，检查 display_profile、readback、renderer、profile、adapter、probe、format gate、模板与 registry；本地对 `2a4ae740..HEAD`、远端对 `345f9f7..HEAD` 的 diff 均成功，日志独立保留。

主独立快照 `/tmp/heater-b02-rereview8-vlhjeuze/snapshot`；显示矩阵使用另一个新鲜 Git 快照 `/tmp/heater-review8-display-yfp1j460/snapshot`。两者均当前源码；普通 Python runtime helper 及补充线型反例只写新证据。全部反例来自最终 `B02-fix-8/candidate/`，其 manifest 为 **`d0eead323cf5ff249da2c20b489d9f1253c4a410890eb3ce0aa5289dcd3df3c4`**。首次模板绑定失败的 `b02-runner-template-binding-failure/`、`gate-result-template-binding-failure.json`、未带 final 的变异材料仅作历史诊断，没有把其输入冒充最终候选；最终候选、final 变异结果和最终 summary 的身份/日志另核对于 `pending-boundary-review.json`。

## 必须修复：[P1] 当前 HEATER_DIM / DIMENSION 的再生成线型来源未纳入校验及签名

位置：`service/src/heater_drawing/drawing/display_profile.py:71/115`，`profile.py:36`，`readback.py:261/529/625`，`scripts/probe_formats.py:208`。共享策略现在校验全部受控图层所引用的 Continuous 定义，并拒绝当前实体/父实体/缓存中越界的线型；但只遍历图层引用，未覆盖**正在使用的 HEATER_DIM 样式及 DIMENSION override 的 dimltype、dimltex1、dimltex2**。readback 只核对固定数值子集和现有缓存；其参考缓存用重建的控制样式生成，并非在真实已加载样式/override 下再生成后比较。page consistency signature 也不绑定这些实际再生成来源。

以最终候选复制完整输入，只增加一个普通虚线表项，然后修改当前使用的样式，无需改变现有缓存、坐标、父层或 Continuous：

```python
doc.linetypes.add('REVIEW_DASHED', pattern=[10.0, 5.0, -5.0])
doc.dimstyles.get('HEATER_DIM').dxf.dimltype = 'REVIEW_DASHED'
# 另两例分别改 dimltex1 / dimltex2。
```

第四例保留原 DIMENSION 的全部必要 override，只追加 `dimltype='REVIEW_DASHED'`。每例同时改首张单页与汇总 DXF，重建全部三页 PDF/PNG 和汇总 PDF，刷新 manifest 中每个 artifact hash，再真实执行完整 `scripts/probe_formats.py --fixture fixtures/synthetic/heater_sample.json --candidate docs/evidence/B02-rereview-8/<case>/candidate --profile dxf_pdf_v1 --output docs/evidence/B02-rereview-8/<case>/validation`。

| 独立完整候选 case | 当前单页/汇总 readback | renderer | 完整 probe | 与正常 page signature | 显式再生成、保存重开后 |
| --- | --- | --- | --- | --- | --- |
| `dimstyle-dimltype` | 接受 | passed | **0 / passed** | 相同 | 尺寸线改用 `[5,5]` 虚线 |
| `dimstyle-dimltex1` | 接受 | passed | **0 / passed** | 相同 | 第一尺寸界线改用 `[5,5]` 虚线 |
| `dimstyle-dimltex2` | 接受 | passed | **0 / passed** | 相同 | 第二尺寸界线改用 `[5,5]` 虚线 |
| `dimension-retained-override-dimltype` | 接受 | passed | **0 / passed** | 相同 | 尺寸线改用 `[5,5]` 虚线 |

四份接受输入均 audit **0 errors / 0 fixes**。在从保存文件重新加载后调用真实 `DIMENSION.render()`，再次保存并重开，原来 BYLAYER 的缓存 LINE 变成 REVIEW_DASHED，独立 `RenderContext` 解析 pattern 为 `[5.0,5.0]`；产品 readback 和 renderer 此时均拒绝（cache display binding drift）。这证明被完整接受的尺寸来源不能保持其声称的受控再生成语义；并非宣称当前未再生成的 DXF/PDF 已有可见差异。

证据：`linetype_binding_review.py`、`linetype-binding-review.json`、原始/补充运行日志、四个 case 的完整 candidate、validation、full-probe.log 与 regenerated.dxf。`visual_binding_supplement.py` 用独立 ezdxf Frontend 绘制已接受输入和再生成结果；已目视检查 `visual/dimension-linetype-comparison.png`，可见尺寸线/界线断开。这里只证明软件再生成及显示解释，**没有目标 CAD 观测**。

另保留 `dimension-override-dimltype` 诊断：最初只替换 override 时丢了必要参数，完整 probe 正确拒绝；它不是成功绕过。随后保留全部原参数的独立新输入才得到上表第四例。没有把第一次诊断改写为成功。

必要修复：把实际引用的尺寸样式及 override 线型来源和定义纳入共享规范化验证/签名；校验真实当前来源再生成的缓存与当前受控显示一致，或在进入该 profile 时明确拒绝越界来源。保留省略/合理等效默认、浮点噪声与**未被引用**的额外 LTYPE 正例。只需关闭本受控原生尺寸链路，不要求通用 CAD 线型 renderer。

## 必须修复：[P2] 待签记录与最终模板及实际审批校验器不同步

`docs/evidence/B02-fix-8/human-approval.json` 的 `candidate.template_manifest_sha256` 仍为 **`1a1e604066096021c90267b9cfaa5e7dab024abaee33a75a763545e4508c73dd`**，而最终模板 manifest 及候选内引用均为 **`f0cb0d964408284f4ea9e7ae85fe03c2673d52ee8d6cc7d77530b14c380b8193`**。最终 candidate manifest、各产物 hash、format decision、registry 的 human hash 及路径本身匹配；不能由这些匹配推断人审记录的模板子绑定也正确。

此外，当前待签 `scope` 五项与 `scripts/check_format_gate.py:15` 的四项 `APPROVAL_SCOPE` 不相等；待签动作有十项（含 `regen`、`close`），但 `validate_approval()` 在第 162 行要求动作 key **精确等于八项**。按当前待签清单真实填完十项，仍会被报 `target CAD edit/update/save/reopen action record is incomplete`。

独立 `visual-binding-supplement.json` 只在内存中进行 test-only 形状诊断，保留人员、时间、输入/输出为空；十项全 true 产生上述动作形状错误，去掉两项后该特定错误消失，其余缺人工证据错误仍在。未写 approved 文件、未伪造人员或批准。范围不相等及所有精确 hash 见 `pending-boundary-review.json`。

必要修复：刷新待签模板 hash 与消费它的 registry hash；把当前待签 scope、动作和实际校验器统一为一个可填、可核验的契约，保留明确的尺寸更新、REGEN、保存、关闭、重开要求。更新后重新核对精确候选/模板/字体/差异绑定；保持 pending 和人员字段为空，由真人填写真实操作事实。

## 第七轮修复及必要回归的独立结果

| 验证 | 本轮实际结果与证据 |
| --- | --- |
| 两种第七轮 Continuous pattern | `[10,5,-5]`、`[1,.5,-.5]` 均组件/renderer/完整 probe 拒绝；complex 定义也拒绝；`display-review.json` |
| 定义规范化与签名 | 粗/细虚线的 layer signature 与正常不同；`[0.0]`、`[3e-14]` 与正常相同；`linetype-binding-review.json` |
| 显示组件/完整输入 | **54 项组件、39 次完整 probe**；34 个完整负例退出 1，5 个正例退出 0；正例全部重建三页 PDF/PNG 与汇总 PDF |
| 合理正例 | 缓存 3e-14 几何噪声、显式默认、Continuous `[0]` / `[3e-14]`、未引用额外虚线定义全部通过，不强行扩大 profile |
| 已关闭父层显示 | 八项旧反例及 0 层、锁定/线宽/plot、父 DIMENSION、INSERT、BYLAYER/BYBLOCK、嵌套 SOLID、组合反例保持拒绝；指定九项退出 `1,1,1,1,1,1,1,0,0` |
| 默认原注册 B01 | **0 / passed**；53 contract + 47 planning、0 skip、10 checks、Node/wheel 均通过；`b01-current/` |
| 默认原注册 B02 | **2 / blocked**；98 format（90.75 s）、198 regression（110.76 s），0 skip；probe 0、dependency 与三个技术 checks passed；仅 human-gate-0/check-format-gate 阻塞；`b02-current/` |
| Windows 独立验证 | **198 passed，0 skip，147.57 s**；五次时间戳重跑均 0；最终候选正常 probe passed、candidate/template immutable；`windows-results.json`、`windows-validation/` |
| runtime 物理文件 | 真实普通 Python helper 正例与恢复正例通过；同尺寸输入/输出变异在 cached/fresh tuple 下均拒绝，删除/原子替换/目录替换拒绝，15 个 retained-token 深层及跨调用/导入变异、11 个版本变异、descriptor/stdout/stderr 实体变异保持拒绝；`receipt-review.json`、`receipt-supplement.json` |
| 字形/尺寸/箭头 | 129 个文字实体、876 glyph、12 SOLID 箭头；最大字形边误差 0.0000170093 mm、箭头 0.0000172347 mm；6 个正常尺寸重复再生成/保存重开稳定，+5/+7 mm 定义点编辑后的测量/文字正确；再生成 glyph 误差 0，碰撞 0 |
| 字体来源 | 原始/展开/再生成阶段实际使用同一 NotoSansCJKsc-Regular，OTF SHA `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`；没有沿用 fallback 测量；`visual-metrics.json`、`dimension-review.json` |
| 颜色/差异 | 三单页和汇总三页各 21 段框线颜色/端点匹配；黄色改黑及仅汇总第二页改黑均拒绝；24 页差异的 349 行内容与测量表逐项对应，2238 cells/34163 可见 glyph 检查通过；`color-review.json`、`difference-audit.json` |
| 旧负例 | 24 个 DXF 异常均拒绝；错误单页、单页横移、汇总第二页横移三次完整 probe 均 1；`mutation-results.json` |
| C02/模板 | 三个 DrawingPage 模型/共享语义通过；最终候选和模板与运行快照字节一致；`sealed-facts.json` |
| B01 依赖与 CLI | 新鲜 clone 正例及十二个绑定负例通过，历史认可仍为 B01-fix-2-r2 原 hash；当前 registry 根/路径及旧 fix-3 污染控制通过；六次真实子进程 CLI 为 `0,2,1,1,1,0`（1 pytest passed），仅测试临时目录，不是实际批准 |

共有 **49 份完整 probe 输入**封存，所有 manifest artifact hashes 实际逐项匹配，见 `probe-candidate-archive.json`。renderer 拒绝的反例保留复制 PDF，不声称成功重渲；成功重渲的输入均完整记录。`review-facts.json` 用独立断言汇总上述结果。默认 runner 正常通过没有覆盖本轮新增再生成反例，二者结论不矛盾。

原执行器 B01/B02 dirty_files=[]。独立 B01 clean；独立 B02 如实记录先前产生的 `?? docs/evidence/B02-rereview8-b01-current/`，非业务漂移。复审主目录的 initial-status 日志是在创建审查归档/证据后采样，含本轮允许写入，不冒称该日志本身为空；最初工具读取的两端状态均为空。只读 `.tools/uv sync --project service --frozen --check` 退出 0、would make no changes，锁 SHA `7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60`。

已实际目视三张最终候选整页、原件三页接触表、覆盖全部 24 页差异的六张接触表、差异第 1/12/24 整页，以及新反例独立显示对照。标题栏、黄色线、引线/尺寸和中文可辨；软件测量不替代图面工程批准。直接 DXF byte-copy/平移 signature 控制仅为软件检查，没有冒称 DXF-DWG-DXF。

## C07：有效当前窗口与额外历史 unknown_external 分别成立

没有发现 C07 实质不满足。最终注册窗口 **2026-11-08 00:17:52.596452–00:17:52.786061 UTC**：before SHA `d2e062576bb9cf13f07d5109c34ce3269239716506e25573345e6c57d8fd1c93`，after SHA `705829b053ae26f471b836d0bdb6256d1714eebef0567bcdd603c53b67eedd9f`。严格 shape/固定覆盖、baseline 实际稳定 hash、同当前源码、24h 时效验证及重新计算 comparison 均通过，unchanged、0 changes。

额外历史 observation `B02-fix-7/b01-boundary-post-run-observation.json` 的 SHA `3e5ed8edee28586658c379b5cb53e649ee629453f0aab2ca0ba92bbe52b99d76` 与第七轮恢复的历史 baseline 重新验证，实际仍为 drawings 工作树变化、attribution=unknown_external；其 source 为历史 `f532dc...b1b7`，没有冒充本轮 `ae7132...e4a7f`。本轮另实际运行独立 before/after CLI 各 0，严格验证 passed/unchanged，见 `boundary-validation.json`。

各窗口只证明各自的事实；不声称整个工作期间外部始终未变，不以 unknown_external 推翻有效注册窗口，也不扩展为无限补 after/全量重跑要求。没有写入、回滚或归因外部项目。完整重算见 `pending-boundary-review.json`。

## 当前候选身份与尚缺真实门槛

以下是被审计的最终候选身份，**不是本轮“可直接送人工闭环”的背书**。先完成上述 P1/P2，再依实际是否重建候选刷新所有绑定。

| 最终 fix-8 文件 | SHA-256 |
| --- | --- |
| `candidate/candidate-manifest.json` | `d0eead323cf5ff249da2c20b489d9f1253c4a410890eb3ce0aa5289dcd3df3c4` |
| `candidate/heater-sample.dxf` | `18ad30a35bcb3888de917ebb3d078c13d6f5047911c116d14e1438fe4d44c64e` |
| `candidate/heater-sample.pdf` | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| `candidate/reference-difference.pdf` | `b194c12a653cde88d4a0486aa98029cfc4b839d0abdc8eca90972e20b325f5cb` |
| `linetype-mutation-results-final.json` | `b75395b25b2c822344bfe2fb4d2ff32be8534367c9484488f9d2776bf37a0881` |
| `b01-runner/summary.json` | `c28201500927ce3eb9dea44325f2f4bcb239bdcd618d96319992aa8b183b8c4c` |
| `b01-acceptance.json` | `1fccbd22eb87e6b70e902cb02a04207caba14034e225ca5683f0bfcfff16467a` |
| `b02-runner/summary.json` | `51da1b2e5c8a304dbb972d8c4f1326e09f739ba9da2e27d0732516b777ff78c2` |
| `human-approval.json`（待修正） | `7a432ffd3d7a6b634a6ccc439ada4b2eec492ee6fffba4cd7ebe55f1a24c0d3b` |

仍需真人审阅：模板/黄色框/字段锚点与测量差异、Noto Sans CJK SC 替代、纸面 5/10/10 mm 引线、原生尺寸行为；当前决定在 `docs/decisions/format-profile.md/.json`、`template-approval.md` 与上述 human-approval。需用户作 DWG 首发范围决定；推荐延期仍不是用户已批准。若要求首发 DWG，另需本项目授权、真实正反转和确切 DWG 的目标 CAD 证据。

目标 AutoCAD 2018 须由具名工程师记录角色、版本、操作时间、精确输入/输出 hash、结构化证据与截图，实际执行打开、轮廓/文字/原生尺寸编辑、显式尺寸更新/REGEN、保存、关闭、重开，核验单位/字体/尺寸。当前 actor/role/time/conclusion 均为空、CAD 动作 false、capability=not_configured，不能用本轮软件回读或 test-only CLI 正例代替。

## 两端原文件保护与交接

分别核对本地 **4419**、远端 **4411** 个原有保护文件，均字节不变；source entries 相同。保留原有本地独有九份 Windows/helper 日志、远端独有根 `.gitattributes` 以及各自 state/events 等既有差异，没有同步改写历史。state SHA 本地 `567ce15237ecfb3feeaa82a9e279fd63c08adc0f3f062d291803722a311ac548`、远端 `df93bfb48ba4d7acf5600b8f509cad250afcff7cd32c1ca36f2664a138ddf57a`，均与各自起点相同。详见保护清单、`source-mirror.json`。

本报告、原字节归档和新证据用 `evidence-index.json` 封存，两端分别独立提交，逐项比较工作树及 Git blob，随后另提交排除自引用的 `git-handoff.json`。交接记录保存内容提交、clean 与两项 diff-check 的实际结果；最终封存提交 ID 在最终回复给出。B02 保持 FAIL/blocked，停手，不进入后续 Batch。
