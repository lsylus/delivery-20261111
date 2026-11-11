# B02 第四轮修复独立复审

结论：**FAIL。F04/F05 仍存在三个可通过完整真实 probe 的错误图面反例，不能宣布技术闭环或仅待人工批准。** 本轮确认多项修复有效，并纠正第三轮缓存 MTEXT 度量的字体回退错误。真实目标 CAD 编辑、尺寸更新、保存与重开、工程批准和 DWG 首发范围决定仍 pending。

本轮只写本报告、上一轮原字节归档 `docs/reviews/B02-rereview-3.md` 和新证据 `docs/evidence/B02-rereview-4/`。归档 SHA-256 为 **70fd26b4422f487bd6891c9fd049f5f738a91c8f351ddb40cfb9a4dbb88d5a40**。未修改业务代码、测试、执行报告、冻结候选、决定及编排记录；未执行 ODA、真实 DWG 转换器或真实 CAD，未借用其他项目许可、未代签批准、未进入 B03。

## 审查对象与身份绑定

本地交接 HEAD `5cda051772a39ac60698e84e0c570d45de39b71a`，实际开始 HEAD `2d37f47715244863ecd015d081f4bc3da4d037c7`，其间为调度文档；远端开始 HEAD `ddee3566bf51c827dce27adf49ad43e65c99b829`。两端分支均为 `codex/b01-foundation`。实际源码契约指纹为 **5017ac4fa7ced0bf6ddb45f1caec3ac02c4f6361cdde273bcef98ff05b98c781**，原根、独立快照及两端最终源码条目相同。纯文档 HEAD 的变化不被机械判作源码失配。

冻结目录 `docs/evidence/B02-fix-4/candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| candidate-manifest.json | f9cb1dd279a1c95bfa9826e9f27910f7509ace48cca0959d244dcc1ee54aea4d |
| heater-sample.dxf | b0c808911dd1b02cd03159b6016b5856763063c67ff1c31a10596bcf7fae9d8b |
| heater-sample.pdf | df89f6ca507a821acbbd6cf06cb55fdff82dfe5876fd20015a9d9f1518d3b852 |
| reference-difference.pdf | 7254d751ae1a423ad8ee830cfb4263fcff01af875b9c04513d96d3f109e52bed |
| drawing-pages.json | a8e5aaae7bf501d90631f7676210643059662e2b5f7fb3027ae5f65b4cf1253c |

模板 DXF hash 仍为 `944dcd371bd06c07670e735801fc57948d1a2d3345d361738368a41ce45e05f1`。最终逐文件核对本地 1,330、远端 1,331 个既有保护文件，均未改变；两端既有 state/events 差异分别保留，远端原有根 `.gitattributes` 也未移植或修改。`sealed-facts.json` 另确认快照的整个 candidate/template 目录与原根完全相同。

已阅读 plan、B02、C02/C05/C06/C07、需求、基线、进度、B01 当前和历史认可事实、第四轮执行报告、旧复审，检查实际修复 diff、实现与测试。未发现适用 AGENTS。变异、重生成和合成政策分支均在隔离副本进行；真实根仅产生本轮审查证据。原始路径、日志、hash 及归档映射见 `evidence-index.json`，两端独立内容提交与干净状态见单独提交的 `git-handoff.json`。

## 独立执行结果

| 验证 | 结果 |
| --- | --- |
| 默认原注册 B01 CLI | **0 / passed**；53 contract、46 planning；十项检查、ECMAScript 与隔离 wheel 安装完整通过 |
| 默认原注册 B02 CLI | **2 / blocked**；53 格式测试、152 总回归通过，0 skipped；DXF/PDF probe 0；实际阻塞项为 human-gate-0、check-format-gate |
| 重新采样真实外部边界 before/after | 两条 CLI 均 0，严格验证器确认 passed / unchanged |
| Windows 完整回归 | **152 passed，0 skipped，退出 0，92.01 s** |
| Windows 时间戳定向测试连续五次 | **5/5 退出 0**；实现已用明确一秒偏移，第三轮偶发等时刻问题关闭，历史失败现场保留 |
| 实际三页 DrawingPage | C02 模型及共享语义验证全部通过 |
| DXF 原十类＋字体/缓存四类＋第三轮六个显示属性反例 | **20/20 拒绝**；另测 text_direction 变更亦拒绝 |
| 错单页、单页 x+100 mm、合并第二页 x+100 mm PDF | 刷新 manifest hashes 后完整 probe 均 **1 / failed** |
| 新尺寸缓存反例 | 改箭头块 SOLID 顶点、MTEXT 内联宽度、缓存 LINE，**三个完整 probe 均错误退出 0** |
| 当前 B01 原始绑定 | 新鲜独立副本正例通过，12 个变异全部 blocked |
| 原有政策矩阵 | 11 项函数矩阵随 planning 运行；另独立重跑六次 B99 子进程矩阵，均符合期望 |
| helper 实际普通 Python 子进程 | 完整日志、超时及子进程组清理通过；旧输出/无输出/普通垃圾/header-only/低熵填充拒绝；高熵合成垃圾仍接受 |

真实远端根 `.venv` 为 Python 3.12.16、PyMuPDF 1.28.2、ezdxf 1.4.5、fontTools 4.68.0、pypdf 6.21.4、Matplotlib 3.11.2、pydantic 2.14.3。`service/uv.lock` hash 为 `7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60`。只读 `.tools/uv sync --project service --frozen --check` 指向真实根 `.venv`，退出 0，未更改依赖；未用临时审图环境替代服务环境。

原始执行与结果见 `results.json`、`mutation-results.json`、`full-mutation-results.json`、`policy-results.json`、`final-checks.json`、`dependency-original-results.json`、`supplement-results.json`、Windows 原始 log/xml 及时间戳记录。Windows 命令索引是事后汇集，明确不冒充运行时签发回执。

## F01–F09 处置

| 项目 | 本轮结论 |
| --- | --- |
| F01 | **关闭**：24 页差异表可读、无单元格越界，源/候选/未匹配展示与数值逐项相符。 |
| F02 | **当前冻结图面的字形对齐关闭**；普通 TEXT 位置已修复。第三轮缓存 MTEXT 超差含审查方法错误，见下文纠正。另保留原生尺寸软件再生成位置变化观察，不冒充真实 CAD 结果。 |
| F03 | 长边引线、尺寸侧别及当前文字/图框/几何碰撞修复保持有效。 |
| F04/F05 | 指定旧反例全部拒绝；**整类未关闭**，三个新缓存/有效显示反例通过完整 probe。 |
| F06 | 精确 DWG、人员/时间/版本/动作绑定及 runner 分支保持有效；改名 Python 旧端到端绕过在当前 Linux/Windows 身份检查中被拒绝。没有实际 CAD/转换正例。 |
| F07 | 只读分离有效，原候选和模板及既有材料字节不变。 |
| F08 | 实际三页 C02 语义有效。 |
| F09 | 改名程序身份防线有效；完整日志/超时有效。**回执组件的真实运行来源/输入绑定及高熵垃圾判别仍不足**，本轮只证明组件缺口，不声称当前完整 Linux verified 绕过。 |
| B01 新模式 | 原始当前报告、源码指纹及 Git HEAD blob 绑定通过；12 变异均阻断，历史唯一认可不变。 |
| 新发现 | PDF 丢失黄色图框，P2 要求偏差；不称为第四轮引入的回归。 |

## 必修 P1：F04/F05 的尺寸缓存验证仍能放行错误图面

位置：`service/src/heater_drawing/drawing/readback.py:383`、`:399`、`:415`，`scripts/probe_formats.py:121`。

原十类负例、arial 字体、DIMSTYLE→Standard、缓存 999、单改位置，以及 STYLE width/oblique、TEXT oblique、缓存旋转、缓存与 midpoint 同步位移、箭头 INSERT 比例均已拒绝，不能再沿用第三轮这些反例指称当前未修复。

新反例直接改变真实候选第一页的尺寸缓存，每次只做一种修改：

| 反例 | 修改与实际图面 | 完整 probe |
| --- | --- | --- |
| arrow_block_vertices | `_CLOSEDFILLED` 共享块 SOLID 的 vtx0–vtx3 均乘 0.1；INSERT 名称、位置、旋转、比例和数量不变。四个箭头实际明显缩小。 | **0 / passed** |
| cache_inline_width | 缓存 MTEXT 原文改为 `{\W0.2;25}`，plain_text 仍是 25，字高、锚点不变；水平尺寸文字明显压窄。 | **0 / passed** |
| dimension_cache_line | 第一尺寸块第一条 LINE 的 start 改为 `(80,185,0)`，尺寸定义点/测量值不变；实际出现错误斜向延伸线。 | **0 / passed** |

每次复制冻结候选，只替换第一页 DXF，按真实 renderer 重生成该页 PDF/PNG、合并 PDF，并刷新 manifest 的全部产物 hashes，再调用**真实 `scripts/probe_formats.py --profile dxf_pdf_v1`**。汇总 DXF 保持原始字节。因此它们同时暴露：错误显示可自洽通过 canonical PDF 比对，且单页与汇总缓存不一致仍未拒绝。并非只测试一个内部函数或省略 manifest。

原因有实证支持：缓存文字检查使用 plain_text，丢掉实际宽度格式；箭头只检查 INSERT 参数与展开后 SOLID 数量，未校验 SOLID 顶点；缓存尺寸线几何未从规划/原生定义独立核验。单页/汇总 signature 只比较几何/尺寸摘要、总边界、普通 text_measurements，未包含这些缓存内容。三种改动均不改变所比较的摘要。9 位浮点归一化本身正确：3e-14 噪声相同、0.001 mm 改动不同；缺陷是比较内容不足。

应从几何和受控尺寸样式推导并核验全部尺寸缓存线、箭头实际形状、有效 MTEXT 格式；在单页/汇总比较中包含这些语义。保持已有旧反例、错页/平移拒绝能力，避免仅加三个特例。

证据：`mutation_check.py`、`full_mutation_check.py`、`full-mutation-results.json`、`full-*/modified.dxf` / `modified.pdf` / `manifest.json` / `validation/` 和原始完整日志。`visual/mutation-comparison.png` 并列原图与三反例，整页及局部均已目检。

## F01 关闭：差异表数值与可读性

独立从原 PDF 路径重新提取轴向、长度至少 5 mm 的线段，换算纸面毫米；原始源线段多重集合与测量记录的 matched＋unmatched 完全相等。三页分别 55/55/65 源段，4 段一对一完整长度匹配/重排，51/51/61 源未匹配；每页 21 候选图框段、17 候选未匹配，候选坐标与 layout 完全一致。

重新计算外底/右/上坐标差 **0.986629 / 0.851027 / 1.184116 mm**；frame-0 横向仅约 0.000011 mm，但端点差 **2.170745 mm**，均明确 relayout，无伪称零差。每页 41 条固定/动态/技术文字与实际 DXF 值相符，原件为轮廓文字的项目保持 unknown。

24 页 PDF 的 **349 行、六列显示值**逐项对应完整测量记录（仅忽略换行空白）；独立可见字形极值检查 **2,238 单元格、34,163 字形，0 越界**。实际字号 5.5 pt，放大后清晰；源端点与未匹配源行现已展示。全部 24 页渲染联系表均目检，并检查第 1/12/24 全页。证据 `difference-audit.json`、`difference_check.py`、`visual/difference-*`。

## F02 当前对齐与第三轮 MTEXT 测量纠正

本轮独立参考不向每个实体强行传入同一 FontFace，而从实体 STYLE 实际解析字体；MTEXT 经 `MTextExplode` **finalize 后**再解析其生成的 TEXT style。分别记录原始、explode 后和原生尺寸再生成后的 requested/resolved 字体、实际文件路径、SHA 与 PostScript 身份。均确认当前使用 `NotoSansCJKsc-Regular`，实际运行字体 hash **e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322**。

PDF 用不透明可见填充路径，经 fontTools BoundsPen 计算真实 Bezier 极值，排除透明检索文字。三页共 **129 文字实体（每页 41 TEXT＋2 缓存 MTEXT）、876 可见字形、12 箭头**，完全消耗对应 opaque fills。与实体解析后的独立 CAD 轮廓逐字比较，当前最大边缘误差 **0.000017010 mm**，箭头 **0.000017235 mm**，均小于 0.1 mm；三个单页与合并相应页像素一致。文字之间、文字对图框和实际 PDF 几何描边无碰撞。

第三轮报告中的缓存 MTEXT 0.125479/0.203965/0.240234 mm 不能作为有效的同字体比较继续引用。重现历史审查环境发现：未 finalize 的 MTextExplode 生成 `MtXpl_Noto Sans CJK SC` 名称，但 style 尚不存在；随后 font_name 回退，实际使用 **DejaVuSansCondensed**，并非锁定 Noto。逐个尺寸重新加载原历史 DXF，六个缓存均重现该回退；finalize 后解析为正确 Noto，文件路径/hash/PostScript 均留档。旧报告与旧证据保持原字节，本报告明确纠正这一审查方法错误。第三轮普通 TEXT 的真实位置超差与此次字体回退分别判断，当前普通 TEXT 修复已通过测量。

另一个独立观察：对当前 DXF 的独立内存副本调用原生 `DIMENSION.render()`，六个尺寸缓存字形均发生 **2.375 mm 纸面位移**，实际字体仍为同一 Noto。例第一页 25 宽度缓存 insert 从 `(88,166.5)` 变为 `(88,168.875)`；HEATER_DIM 的 `dimtad=1`、`dimgap=0.625`，覆写 dimtxt=3.5，相关定义和前后属性见 `sealed-facts.json`。这与当前缓存对齐通过是不同检查，说明仍需解释再生成语义/样式与缓存之间的关系；**仅是 ezdxf 软件再生成观察，未据此声称 AutoCAD 已失败或已通过**。不得将字体身份一致等同于真实目标 CAD 编辑更新后位置一致。

字体 profile 的来源为系统 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc` SC face 2，文件 hash `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`；许可为 SIL OFL 1.1，系统包版权文本已归档 `font-package-copyright.txt`。实际度量的是上述独立 OTF，未把原样件 SHX 的存在冒称为已使用。

最终证据 `visual-metrics.json`、`visual_check.py`、`sealed-facts.json`。`visual-metrics-first-run.json` 保留早期诊断同一文档反复 finalize 的局限，最终历史诊断为每个尺寸重新加载。`additional-facts-first-run.json` 误把填充字形自身的 LINE 路径计作几何，最终版只取实际描边，结果为 0 碰撞，不沿用初始假阳性。

## P2：PDF 丢失明确要求保留的黄色图框

`docs/reference/requirements.md:59`（R03）及 `docs/contracts.md` C06 要求保留黄色图框。当前每页 DXF 有 **12 条 FRAME_YELLOW LINE，图层 ACI=2**；独立按其端点坐标定位实际 PDF 对应线段，36 条均为 **RGB (0,0,0)**，三页 PDF 实际描边只有黑色。`pdf_renderer.py:185`、`:192` 对 LINE/LWPOLYLINE 硬编码 black，未使用受控图层颜色。

这不是坐标误匹配：各匹配端点误差低于 0.001 mm。未发现批准单色输出的例外。本轮首次发现此当前要求偏差，不推断它由第四轮引入。应按受控颜色策略输出并验证 DXF/PDF 的图框颜色。证据 `additional-facts.json`，候选三页已目检。

## F06/F09：身份与政策修复成立，回执组件仍有局限

当前身份核验不再只依赖 basename/ELF。真实普通 Python 复制并改名 ODAFileConverter，副本未执行：Linux 因缺可信 vendor signature/digest 判 **available_unverified**；Windows 真实复制 python.exe 后改名 ODAFileConverter.exe，因缺有效 ODA Authenticode 身份同样 **available_unverified**。Linux 原程序 hash `23bc148d2b48964b621c5561ff2b81c1d9c7b717967a7491efbf12f4304882b5`；Windows `7283f7d271f7de55cc7fd290efbcc274119655f99bfb676de7f1036e2fc59e08`。没有执行或归档这些改名二进制。

在同一隔离 Git 副本中，为合成政策输入重新采样真实边界、运行真实 B01=0，再提交仅该副本的 registry/B01 binding，随后五次运行完整原注册 B02，真实冻结候选与业务测试不变：

| 完整政策场景 | 退出码 / 状态 |
| --- | --- |
| 合成 postpone | 0 / passed |
| pending | 2 / blocked |
| postpone＋配置未可信转换器 | 0 / passed |
| required＋未验证 | 1 / failed，gate blocked |
| required＋改名 Python 自称 verified | **1 / failed，gate blocked** |

脚本沿用的 `postpone-contradictory` 名称现在不代表真矛盾：其 capability 已是 unverified，因此 postpone 通过合理；`required-claimed-verified` 也仅是自称 verified，不能按旧报告说它已 verified。政策副本因 registry 变更产生不同 source 指纹，不冒称原始 B01 认可。

独立重复现有六次受控 B99 CLI 矩阵：postpone 0、pending 2、postpone 真矛盾状态 1、required blocked 1、required fake verified 1、required controlled positive 0。另在 gate 入口**直接注入明确标记的合成 verified fixture**，只隔离检查精确 CAD 绑定：结构正例 0；无关 DWG、缺 operator、未来操作、错误版本、缺动作各 2。此 fixture 不证明 capabilities 接受转换，也不是实际 CAD 认可。

回转语义签名直接读真实合并 DXF：字节复制签名相同，将 HEATER x+1000 mm 后不同（`sealed-facts.json`）；没有以先触发的身份拒绝冒充坐标语义已被隔离验证。

仍须解决的组件问题（P2，位置 `dwg_adapter.py:59`、`:78`、`:193`、`:284`）：

1. `_command_evidence` 接受本轮自行写入的 JSON controlled record：虚构 PID=12345、started=finished=0，record 内输入路径/hash 故意错误，只在外层 item 自填正确值，返回 **None（接受）**。实际 helper record 本身也未记录并绑定输入 hash，不能证明运行时处理了那份确切输入。`record_kind/schema_version` 是内容标签，不能证明来自 helper 的真实执行。
2. `_version_execution_error` 对完全自写的版本回执返回 **None**，其中 finished=0、started=999，未发生任何版本运行。Authenticode 身份检查证明程序签名，与回执是否实际运行是两项事实。
3. helper 对 **AC1032＋bytes(range(256))*8** 退出 0 并接受；它是确定的非 DWG 合成字节，熵为 8，可绕过 header/长度/熵启发式。低熵填充已拒绝，不能把启发式通过称为结构有效。

证据 `supplement-results.json`、`fabricated-receipts/`、`helper/`。这些探针只调用内部回执组件；**没有绕过当前非 Windows 身份防线，没有证明当前完整 capabilities 在 Linux 仍会 verified，也没有真实可信 Windows ODA 正例或端到端绕过证据。** 应把可信执行入口的输入字节、命令、输出和原始日志直接绑定，校验时间与版本执行；高熵垃圾仍不能作为有效 DWG。保留已有效的身份拒绝和许可范围规则。

真实 helper 普通 Python 回归：exit 7 保留 stdout/stderr 各 6001 字节；0.15 s 真超时保留各 12 字节，Linux 子进程 sentinel 未出现；旧输出、无输出、普通垃圾、header-only、低熵填充均拒绝。没有把 Python helper 当作真实转换器验收。

## B01 当前依赖绑定

当前原始 `docs/evidence/B02-fix-4/b01-runner/summary.json` hash **f9f0860b928c66af526a34a6ae2e7f6d6da80c1ddff270dfb3a32150e9101cda**；执行 source HEAD `85aaa2c22ac079e479be07ca41076e7f736bd71f`，binding 提交 `fc39bc4c4046e43aadc6f317815c3ecaf60f21ea`，binding hash **03a86a11ef586ab17d3941ca5695ab875a728b8c9c4bce08997c5a0636378620**。历史唯一认可仍是 `B01-fix-2-r2/summary.json`，hash **fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0**。

独立实际 B01、真实边界均通过。另一新鲜副本使用原始指纹、原始摘要与 Git 控制绑定，正例 passed；删命令、argv=true、删 boundary check/input、错 source/status、未来/过期时间、错日志/输入/产物 hash 共 11 项 blocked；同步重写工作区 binding 的第 12 项由 Git HEAD blob 比较阻断。四条必需命令、十项检查、原始日志和输入产物均参与校验。默认 B02 接受当前报告的纯文档后续 HEAD，没有用影响声明代替本轮实际重跑。证据 `dependency-original-results.json`；原报告/绑定受保护清单核验未改。

## 交接边界

优先修复三个完整 probe 反例所代表的尺寸缓存验证缺口，补图框颜色，并补回执输入/执行来源与有效 DWG 判别。保留本轮已经通过的差异表、当前字形对齐、指定负例、身份检查、政策矩阵、B01 及 Windows 时间戳修复；不要重新引用已纠正的旧 MTEXT 测量作为失败证据。对软件尺寸再生成位移作明确解释，并在真实授权的目标 CAD 流程中核验更新后的行为。

技术问题尚未关闭，本轮不请求工程批准或宣称仅剩人工步骤。审查材料在两份独立仓库分别有意提交，索引绑定报告、历史归档和本轮证据；Git 交接记录另行提交避免自引用。**FAIL，止于 B02。**
