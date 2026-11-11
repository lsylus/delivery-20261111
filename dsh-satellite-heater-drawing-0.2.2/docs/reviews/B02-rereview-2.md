# B02 第二轮修复独立复审（F01–F09 及 B01 依赖模式）

结论：**FAIL；仍有具体技术缺陷，尚不能称为“技术已闭环、可送人工”。** 真实 CAD、工程批准及 DWG 范围决定也仍 pending，但本结论并非仅由这些外部门槛造成。

上轮报告按原字节归档为 `docs/reviews/B02-rereview-1.md`，SHA-256 `7f8791fd207f5d36712291fe3c6be0ae17de29503835937183dd33a287654b98`。`B02-initial.md`、历史审查/执行证据及各自编排记录均保留。新独立证据仅在 `docs/evidence/B02-rereview-2/`。本轮没有改业务代码、测试、候选、执行报告、格式决策或 state.json，没有执行 ODA/真实转换、借用其他项目许可、代签批准或进入 B03。

## 绑定与独立执行

本地交接 `dc73d469b94382032667d5797bc2f62ea364dcc5`，实际开始 `adec57b3b8960bf6d9ef09e4c6ca682247e65ffc`（仅多调度记录）；远端开始 `a48920c012118e8340ab3539cf2481c2bb3da23f`。两端分支 `codex/b01-foundation`。独立源码契约指纹为 `9424d8963356c6c7092ab8cbc2d4f07fe5237d8928ea9184a08db76e4e3603de`；不把纯文档 HEAD 变化误判为源码失效。

冻结候选 `docs/evidence/B02-fix-2/candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| candidate-manifest.json | `67b9672e2f3a338cc8e9015888150b419d9f28edc55ce976f50774ed029567b3` |
| heater-sample.dxf | `9b893f26a4f7c17d72fc72d5b280c2c996056bce1c37f91fb1ee3fc7fc6f80f4` |
| heater-sample.pdf | `df1b40d58945e47347d6008a7d871827ca58c001a73c56168097cb0ba2d552bd` |
| reference-difference.pdf | `4f3960d16260549066567b958fdea4fc967e4607e2ac77887b9f354574d20a8a` |

已真实读取计划、B02、C02/C05/C06/C07、需求、进度、执行报告和上轮复审；查找本地祖先/项目及远端适用 AGENTS，未发现适用文件；读取实际实现和修复 diff。以下命令在独立 Git 快照运行，注册项、业务实现和测试均未修改：

| 验证 | 独立结果 |
| --- | --- |
| 默认 B01 runner | **0/passed**：contract 53、runner 34 tests passed，ECMAScript 与 wheel 隔离安装退出 0；注册边界检查通过 |
| 默认 B02 runner | **2/blocked**：36 格式测试、123 总回归 passed，0 skipped；DXF/PDF probe 0；DWG 非必需事实 2；真实 blockers 恰为 human-gate-0、check-format-gate |
| 当前源码真实新 before/after 外部边界 | CLI 均退出 0；同一严格校验器重新核验 source-boundary **passed / unchanged** |
| 正常三页 / C02 | 三页模型、公开语义契约、汇总及单页 DXF 均通过；原生尺寸及 12 箭头保留 |
| 原五例＋第二轮新增五例 | **10/10 拒绝**；错误单页 PDF 重 hash 后也拒绝 |
| 新同类反例 | 字体替换、DIMSTYLE 字体漂移、尺寸缓存文字 999 仍接受；单页或合并页平移 100 mm 重 hash 后仍通过 |
| 只读与保护 | 独立 probe/完整政策分支前后 candidate/template 全文件 hash 相同；原仓库保护清单不变 |

独立重渲染并目检源 PDF 三页、候选三页、两页差异 PDF 和平移负例；候选三个单页与合并对应页逐像素渲染相同，无整页位图替代。原始命令、argv/cwd/退出码/日志见 `results.json`、`policy-results.json`、`dependency-pruned-result.json`；路径归档映射与全文件 hash 见 `evidence-index.json`。负例批准/许可/转换记录均明确是审查用合成材料，绝非真实授权、转换或人类签收。

## F01–F09 结论

| 项目 | 本轮处置 |
| --- | --- |
| F01 | 两处原文字越界已修复；测量映射仍错配文字笔画且覆盖不完整，未关闭。 |
| F02 | cap height/em 主因已修；真实字形宽度/位置仍超过 0.1 mm，未关闭。 |
| F03 | 原长边引线/长度尺寸冲突修复保持有效。 |
| F04 | 冻结候选的 DIMSTYLE 和 virtual MTEXT 均正确引用 HEATER_CJK；验证器仍接受实际字体/样式替换，未关闭。 |
| F05 | 指定十反例和错页 PDF 均拒绝；纸面位置与尺寸缓存内容仍误放行，未关闭。 |
| F06 | 空壳/无关 CAD、未来时间拒绝，完整延期 runner 已走通；DWG 必需路径及精确证据绑定仍有缺口，未关闭。 |
| F07 | 构建与只读验证分离保持有效，候选和模板前后字节一致。 |
| F08 | 公开 C02 DrawingPage 保持有效，三页均通过。 |
| F09 | 非零/超时完整日志、垃圾/旧输出拒绝和 Linux 子进程组清理已修；假 DWG/几何漂移仍可 verified，未关闭。 |
| B01 新模式 | 当前真实 B01 检查通过、历史认可事实保留；依赖摘要完整性仍可绕过，须修复。 |

## 必须修复的技术缺陷

### F01（高）：测量映射仍会把字形笔画当作图框，产生误导性的接近零差值

位置：`scripts/build_format_candidate.py:41` 的 `measure_reference`。

已不再硬编码三行零，变换、±0.15 mm 不确定性和字段待审说明也已增加。但线匹配只按坐标最近且区间稍有重叠，缺少线段长度、端点、覆盖率、对象身份和未匹配项约束；短字形笔画会通过方向容差筛选。

冻结 `reference-measurements.json` 中，候选 **200 mm** 的 outer-bottom `[5,5,205,5]` 被配到源 `[190.147222,5.034146,189.988468,4.970648]`，长度只有约 **0.171 mm**，却展示差值 **-0.002 mm**；outer-left 的 287 mm 边被配到约 **0.162 mm** 的字形笔画。frame-2 的全宽分隔也选中了左登记条短线。这些数字有计算过程，配对对象却不成立，不能当作图框一致证据。

当前只从源第一页提取并为候选 21 段挑最近线；未列出源图框遗漏线、全部固定文字/技术段落和三页动态字段的完整对应/有意差异。差异 PDF 总体可读，但第二页 `field-standards_reviewer` 跨第一列边界，需调整列宽或换行。源图与规范化模板存在已知重排，工程批准可以接受差异，但不能代替先生成正确的测量证据。

验收：以完整线段和明确对象身份匹配源/候选；排除字形笔画，列未匹配/新增/删除/重排项；无法原生测量的字段明确标未知及依据，不伪装近零对应。保留纸面变换和不确定性，修正差异表可读性后再送审，不要求预先解析未授权 DWG。

### F02（高）：换算修复后仍有可测字形宽度差异

位置：`drawing/pdf_renderer.py:37`、`drawing/text_metrics.py:78`。

独立读取锁定 SC 文件（hash `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`），确认 `unitsPerEm=1000`、`sCapHeight=733`，并注册到 ezdxf 后核对解析出的 PostScript 身份。直接 fontTools 字形轮廓/advance 与 ezdxf 路径宽度互相核验；PDF 用实际字符 origin/size 与同一字形轮廓计算，未使用上轮静默 fallback。

三页各 **41** 条普通 TEXT 均匹配到 PDF，包括 PDF 合并成同一 span 的相邻字段。独立测得实际原生字形框未与图框/其他普通文字碰撞；“旧底图登记号” x=**5.334895…25.178005 mm**，KX 图号 x=**146.721041…201.880659 mm**，两处原越界确已消除，箭头/尺寸侧别/1:2 几何亦正确。

但普通文字仍由 Matplotlib 独立排字，CAD 度量与 PDF 排字的字距/对齐尚未一致：

| 图号 | 同一字体直接轮廓宽 / ezdxf 路径宽 mm | PDF 实际轮廓宽 mm | 宽度差 mm |
| --- | --- | --- | --- |
| CX-29-KR05-XM01 | 44.338336 | 43.989056 | 0.349279 |
| CX-26-KR05-DLL-01 | 48.354707 | 47.840587 | 0.514120 |
| KX-11-WR-100-300-M1 | 55.159618 | 54.740254 | 0.419364 |

相应边缘位置最大差为 0.178/0.262/0.336 mm。CAD 单词“CAD”的 cap height 换算已基本一致；三页中间对齐基线另有约 0.092 mm 差。以上是软件一致性测量，不冒充目标 AutoCAD 的最终显示验收。证据 `visual-metrics.json` 保存全部文字框、字体身份、维度和测量方法。

验收：统一实际字距、字形位置和基线/对齐规则，避免仅共享字号公式而继续使用不同排字规则。对全部普通文字和尺寸字形、箭头与边界记录实测误差及碰撞，达到契约 0.1 mm 纸面映射要求后再宣称一致；目标 CAD 仍须另验。

### F04/F05（高）：回读未核对真实样式文件、DIMSTYLE 关联和尺寸缓存显示内容

位置：`drawing/readback.py:103`、`:298`。

冻结原候选中 `HEATER_DIM.dimtxsty=HEATER_CJK`，六个尺寸的 virtual MTEXT 也均为 HEATER_CJK，清单锁定 SC 面、hash/许可，正文覆盖有效。这一正例成立。但对 CX-29 单页只分别做以下变异，`inspect_dxf` 全部接受：

1. 把 HEATER_CJK 样式实际字体改成 **arial.ttf**；实体仍叫 HEATER_CJK。
2. 把 HEATER_DIM.dimtxsty 改成 **Standard**，保留原缓存块；当前 virtual 文本仍叫 HEATER_CJK，目标 CAD 显式重生成时将换样式。
3. 把原生尺寸关联块里的 MTEXT 从 25 改成 **999**；真实 measurement 仍为 25，style 及箭头数不变。

见 `readback-mutations.json` 与 `mutations/`。当前只是验证了样式名称和几何测量，未验证样式解析的字体文件/属性、DIMSTYLE 的真实关联及缓存显示文本。不能把这些反例算作“目标 CAD 隐式替换通过”。

验收：核对实际使用的样式表、DIMSTYLE/override、可解析字体及 hash/许可/覆盖；检查缓存显示字符串与预期尺寸、字形及显示位置，必要时比较受控重生成结果。三例必须拒绝，正常三页及已修十例不得回退。未使用的 ezdxf 默认样式不被误要求全部打包。

### F05（高）：逐页 PDF 位置/图形一致性仍未验证

位置：`scripts/probe_formats.py:51`。

错页替换并重 hash 已会失败。但在隔离副本中，对正确 CX-26 单页 PDF 的整个内容流施加 **x+100 mm** 变换并正确重 hash，实际完整 probe **退出 0/passed**；对合并 PDF 的第二页单独做相同变换也 **退出 0/passed**。渲染可见大量内容被推到纸外，见 `visual/shift-single.png`、`pdf-counterexamples/` 及原始日志。

单页验证只检查预期文字子串、页数/纸型、无 Image、内容流足够长；合并页只查 code/name。它们不检查文字实际位置、可见性、几何/原生尺寸及单页与合并页的渲染等价。hash 正确只说明确切验证了错误字节。

验收：对最终可见矢量、字形/尺寸位置及裁切做与 DXF/规划一致的测量；合并页须对应已通过单页的内容/渲染，而非只含同代号。两种平移负例必须拒绝，原三页仍通过。此项限 B02 已交付三页，不要求提前实现 B05 整套交付业务。

### F06/F09（高）：DWG 必需分支仍不一致，伪造记录仍能 verified

位置：`drawing/dwg_adapter.py:55`、`:88`、`:141`，`scripts/check_format_gate.py:85`，`scripts/verify_batch.py:637`。

有效改进：原垃圾 DXF 反例现在保持 available_unverified；普通垃圾、header-only、旧输出和非零退出均拒绝。独立实际退出 7 程序的 stdout/stderr 各 **6001 字节**完整保存；超时两流均保存，Linux 子进程 sentinel 未出现，确认进程组清理有效。证据 `helper-results.json`、`dwg-counterexamples/logs/`。

仍有三处问题：

- 将真实有效的候选 DXF 作为输入，仅把回转 DXF 的加热器轮廓移到 **x+1000 mm**，保持类型数量、文字和尺寸 measurement 不变；DWG 为 **AC1032+2048 个 x**；“转换器”仍是普通 Python，产品/版本仅在 JSON 自称 ODA；argv 写 `python -c pass`，双流为空文件。所有路径/hash 匹配后，capabilities 返回 **verified_evaluation_only**。没有执行转换器。当前 signature 根本不含坐标/轮廓/样式/布局等，元数据与长度阈值也不证明 DWG 有效或命令实际执行。见 `dwg-counterexamples/changed-license.json`、`results.json`。
- DWG CAD 记录仅检查另一组独立 DWG 的头/大小、动作布尔值、JSON 和截图头，不绑定到刚核验的转换 DWG，也缺少该 DWG 操作的独立人员/时间/版本/语义核验。独立 required 分支可使格式 gate 对上述假 verified 和另一对垃圾 DWG 给 **passed**。
- 完整 runner 的 `format_evidence_checks` 却无条件要求 DWG status=blocked/未运行。因此上述格式 gate passed 时，完整 runner **退出 1**，唯一错误为 `DWG evidence does not truthfully record the unrun blocked probe`。即使未来真正合法验证也会遇到同一硬编码矛盾；当前没有通过完整真实状态机的 DWG 必需正分支。

完整政策测试并非只调用一个函数：在隔离副本配置一次合成批准后，重新真实采样边界并运行 B01=0，随后实际注册 B02 的延期分支 **0/passed**；未来决定 **2/blocked**；DWG 必需但未验证 **2/blocked**；声称 verified 的必需分支 **1/failed**。原代码/测试未改；只有隔离副本的证据和 registry hash/对应源 Git 绑定用于测试。详见 `policy-results.json`、`policy-*/`。真实原件仍 pending；这些合成通过不能替代人类批准。

验收：保留 helper 已通过回归；授权可用与已实际验证分开，实际版本/执行程序/双向命令/完整运行记录须可靠绑定；回读语义包含坐标、矩形/引线/样式/尺寸/中文/布局等承诺要素，垃圾 DWG 不得靠扩大字节数通过。DWG CAD 输入须绑定确切转换结果及其独立操作证据。格式 gate 和 runner 按最终真实决定处理相同状态；完整延期及必需正反分支均须可核验。无需且不得为此次修复擅自调用 ODA 或其他项目许可。

### B01 依赖完整性（高）：current_source_contract 可接受被裁剪/改写的当前摘要

位置：`scripts/verify_batch.py:196`，尤其 `:234`、`:268`。

新当前 B01 summary 的原始 SHA-256 确为 **5c74f140f39889788911f8b334072984458d5e5ea79430ccb2c075172efd1777**。它的当前源码指纹、全部现有日志/输入/产物 hash 和状态均核验通过；本轮默认 B01 也真实重跑通过，当前注册边界和另取的真实新边界均有效。历史唯一认可 `B01-fix-2-r2/summary.json` 的 hash **fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0** 未改变且 registry 保留其 path/hash。历史事实不因当前 uv.lock 更新或文档 HEAD 变化而废弃，也不能代替本轮新 B01 检查。

避免把当前 summary hash 嵌入源码指纹、造成自引用，是合理目标；当前实现却只核验摘要“还列着”的条目，不核验应有的完整集合，也没有在另一份非自引用的受控凭据中绑定获认可的确切当前报告。独立反例：删除四条必需命令中的后三条、删除 source-boundary check、删除 boundary before/after 输入、将命令 argv 改为 `true`，各例仍为 dependency passed。错误 source/status、过期/未来时间、日志/输入/产物错 hash、历史认可错 hash 会拒绝，确认这些防线有效。

进一步把上述裁剪合并到同一副本 B01 摘要，通过**真实默认完整 B02 runner**重跑：dependency-0 仍 **passed**，总退出 2 仍只列原有两个人工 blocker，没有发现必需 B01 证据丢失。见 `dependency-mutations.json`、`dependency-pruned-input.json`、`dependency-pruned/summary.json`。当前源码指纹和历史报告 hash 均未被伪造。这说明新的消费模式尚不符合 C07 的摘要完整性要求；并不否认本轮实际运行得到的 B01 正向证据。

验收：核对依赖 Batch 的完整命令 id/required/argv/执行语义、必需检查及输入/产物集合，特别是完整 source boundary 证据；当前报告需通过源码指纹之外的受控认可/摘要绑定来避免自引用，而非任意改写后重新接纳。保留现有时效、源码、历史认可及逐文件 hash 校验。上述裁剪/argv 负例须拒绝，真实新 B01 和仅文档 HEAD 变化仍应接受。复审不改 registry/历史报告或代建认可凭据。

## 剩余外部门槛与风险

技术缺陷修复后须重新冻结并绑定最终源码、模板、字体和候选，重新独立复核；本次列出的 hash 是当前候选身份，不是批准凭据。

真实工程审阅仍须具名人员、AutoCAD 2018 或用户明确批准的目标 CAD、确切输入 DXF，编辑轮廓/文字/原生尺寸、显式更新标注、保存重开，记录人员/版本/时间/前后 hash、可读截图及结论。另批准正确的源/候选差异与模板重排、SC 字体替代和引线 5/10/10 mm；用户基于最终新证据决定首版延期 DWG 或要求 DWG。若要求 DWG，须本项目授权实际转换与确切 DWG CAD 操作证据。软件路径度量、合成状态机或回转成功均不代替上述签收。

审查环境说明：远端默认 .venv 的 `import pymupdf` 实测失败，尽管 pyproject/uv.lock 已新增该依赖。独立渲染使用审查专用 `/tmp/heater-b02-review2-pdf` 中的锁定 1.28.2，未安装到服务 .venv；后续应使实际环境与 lock 一致并记录构建环境。此环境事实不被测试通过掩盖，也未用于改写冻结候选。

仅提交本报告、上轮报告原字节归档及 `B02-rereview-2/`。完整保护清单、源指纹/镜像核对及内容提交后的双端 clean 检查见新证据；`git-handoff.json` 随后单独提交，最终 HEAD 以两端 git log -1 为准。两端既有调度状态分别保留，不覆盖、不进入 B03。
