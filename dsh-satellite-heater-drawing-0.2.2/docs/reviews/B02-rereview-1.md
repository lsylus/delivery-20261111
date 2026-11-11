# B02 修复后独立复审（F01–F09）

结论：**FAIL，技术修复尚未闭环，不能转人工签收或宣告 B02 PASS。**

本轮复审 B02-fix-1 冻结候选及九项修复，不修改业务代码、测试、执行报告、历史证据、候选或 state.json。原独立审查已按原字节归档为 `docs/reviews/B02-initial.md`，归档绑定见新证据目录 `docs/evidence/B02-rereview-1/` 的 `archive-binding.json`。本轮没有运行 ODA 或任何真实 DWG 转换器，没有创建真实批准、修改格式决策或进入后续 Batch。

## 审查绑定与复现结果

- 本地开始 HEAD：`c96e55a87db69aa6e3b2bffdde7c1ee756727928`；执行器交接本地 HEAD：`e130ff8a90e45efe00dbb3995d4a1c3c0ae89fad`；远端开始 HEAD：`459f9c77de68e23bbd3c2eaef34941ad3f7225da`。分支均为 `codex/b01-foundation`。调度文档后续提交不被机械地视为源码漂移。
- 独立计算源码契约指纹：`4441ab39a758d962d8cc561e805c81edf25176d9368f6112588849296be4d578`，与执行报告及冻结 runner 一致；其引用的输入、产物 hash 全部核实，没有错绑。
- 冻结汇总 DXF：`f8e4bba9156fc19d57b9a4b2890c174cbefc9da35658785244423c881aeb34b1`；汇总 PDF：`56acc618c9ce8846821374f0d7f8dde358f48ed1d898694229f55d39d7e56104`；manifest：`d0dc75b359a75f828539332dbe622103421bb74e09765a7bef6f976f1af79097`。完整文件绑定见 evidence-index。
- 在独立 Git 快照运行未改动的注册 B02 runner：退出 **2/blocked**。DXF/PDF probe 退出 0，失败测试 **23 passed / 0 skipped**，回归 **107 passed / 0 skipped**；DWG probe、格式 gate 退出 2，真实 human gate 仍 pending。测试通过不抵消下列独立反例。
- 独立解析、渲染并目检源 PDF 三页、候选三页与差异表。候选三个单页与汇总对应页逐像素渲染一致；顺序、纸面 A4、轮廓 25×25 / 30×50 / 100×300、原生尺寸、箭头和可编辑字段均有正向证据。PDF 内容没有被栅格化为整页图片。
- 命令、工作目录、退出码、原始日志及 hash 见 `results.json`、`supplement-results.json`；运行时路径到归档路径映射见 `evidence-index.json`。所有假批准、假转换与变异文件均为隔离负例，**不代表人类批准或转换能力**。

## F01–F09 逐项结论

| 项目 | 本轮结论 | 已修复与仍需处理 |
| --- | --- | --- |
| F01 模板忠实度与文字越界 | 部分修复，未关闭 | 标签、聚酰亚胺及 O3=郑玲已恢复；图框/标题栏仍有未量化的重排，原生文字仍越界，四行硬编码表不能证明完整复刻。 |
| F02 PDF 与 CAD 尺寸/方向/字宽一致 | 部分修复，未关闭 | 12 个箭头、竖向尺寸文字、1:1/1:2 已修正；普通文字把 CAD cap height 当 PDF em size，实际字宽不一致。 |
| F03 长边出线冲突 | 原具体冲突已修复 | 30×50 页长度标注移到右侧，原引线交叉已消除；全页包围盒/避让承诺仍受 F01/F02/F05 缺口限制，不能宣称完整零碰撞。 |
| F04 实际字体与覆盖 | 部分修复，未关闭 | 普通文字锁定 SC 第 2 面及 hash，最终正文 171 个 codepoint 覆盖通过；原生尺寸仍用未声明的 OpenSans 样式。 |
| F05 严格回读 | 部分修复，未关闭 | 原五反例均拒绝；新增五个同类 DXF 反例及错误单页 PDF 仍通过。 |
| F06 人工/格式 gate 与 DWG 延后路径 | 部分修复，未关闭 | 空批准、错 hash、错误 scope 等检查已增强；空壳 CAD 证据和未来决定仍接受，完整延后 runner 仍阻塞。 |
| F07 只读验收/受控模板 | 原问题已关闭 | 构建与验收分开，模板受控 hash/结构核验；独立 probe 前后模板及整套候选字节完全相同。 |
| F08 C02 DrawingPage | 原接口问题已关闭 | 三页均经公开 DrawingPage 模型及语义契约验证，包含 revision/template/scale/geometry/placement/fixed_text_version；不再使用原自创 SamplePage。 |
| F09 DWG 状态真实性/helper | 部分修复，未关闭 | 普通垃圾、旧输出、非零退出被拒，Linux 子进程组超时清理实测通过；假正反转文件仍能升级 verified，失败日志仍不完整。 |

## 仍须执行器修复的技术项

### F01/F02（高）：CAD 与 PDF 字宽不同，原生候选仍越界

位置：`service/src/heater_drawing/drawing/pdf_renderer.py:36` 的 `_draw_editable_text`，以及 `templates/heater-a4-v1/layout.json` 的文字锚点/高度。

渲染器把 DXF `height` 直接换成 PDF 字号，忽略 CAD 大写字母高度与字体 em 的关系。锁定 SC 字体 `unitsPerEm=1000`、`sCapHeight=733`。原候选三页 PDF 的“CAD”文本跨度宽 **9.669344 mm**；用同一 SC 字体直接读取 hmtx 并按 DXF cap height=5 mm 计算为 **13.192360 mm**，相差 **3.523016 mm**，远超报告的 0.1 mm。注册相同字体后的 ezdxf 度量与直接字体度量一致。

直接读取锁定字体轮廓测得：三页“旧底图登记号”轮廓 x 范围 **7.392224…27.235334 mm**，越过 x=**25.5129 mm** 分隔线；KX 页图号轮廓右端 **206.710778 mm**，超过 x=**205 mm** 右边框。当前 PDF 字号较小，目检看似容纳并不等于原生 DXF 合格。这是当前冻结候选的实际缺陷，不只是门槛反例。见 `native-font-confirmed.json`、`pdf-inspection.json`。

证据更正：初次 `dxf-inspection.json` 和 `supplement-results.json` 的 native-width/bbox 使用了未向 ezdxf 注册的字体，发生静默 fallback；这两处宽度/包围盒值不作为结论依据。保留原始记录，并由 `native_font_check.py` 的直接 fontTools 度量和已核对字体身份的 ezdxf 结果替代，详见 `native-font-confirmed.json`。

此外，`scripts/build_format_candidate.py:40` 的差异 PDF 只有四个硬编码项目，三项差值固定写为 `0.0000 mm`，没有对模板全线条/字段/原图坐标进行独立测量。独立 PDF 路径采样显示，源第一页标题区存在 y=**33.77847 mm** 的横分隔，候选采用 y=38/27/16 mm 的不同分割；外框/左侧登记条也仍有不同。原 PDF 不是原 DWG 坐标真值，但这些差异必须测量、说明变换与不确定性并列入工程批准，不能用四行表声明完整复刻。源/候选完整视图和裁剪见 `visual/`。

修复验收：统一 CAD/PDF 的真实字体度量、宽高因子、基线和对齐；针对三份小样测量实际字形、图框、尺寸、引线的纸面包围盒及碰撞。修复上述两处越界；提供源/候选完整坐标与差异映射，明确允许的重排和待批准差异。0.1 mm 如作为验收阈值须实测，不能仅返回常数。

### F04（高）：原生尺寸字体仍在清单之外

位置：`drawing/dxf_writer.py:172`、`drawing/readback.py:94`、`templates/heater-a4-v1/fonts.json`。

`HEATER_DIM` 只创建而未绑定 `dimtxsty`；实际原生 DIMENSION 虚拟 MTEXT 仍引用 `OpenSansCondensed-Light`，清单 CAD 依赖只声明 `NotoSansCJKsc-Regular.otf`。普通 TEXT 的 SC coverage、PDF 检出 SC 字体，均不能证明尺寸样式受控。`dxf-inspection.json` 保存全部样式和每个尺寸的实际引用。

修复验收：明确锁定所有尺寸/文字样式及可供目标 CAD 使用的字体文件、hash、许可来源与替代批准；对样式实际解析出的字体核验，缺字体必须失败。不得依赖目标 CAD 的隐式替换。字体替代和真实 CAD 结果最终仍需工程签收。

### F05（高）：验证器仍接受尺寸/纸面漂移和错误 PDF

位置：`drawing/readback.py:79`、`:94`、`:129` 及 `scripts/probe_formats.py:65`。

原来的尺寸 text=999、错误 viewport 比例、引线移出纸面、错误电阻、三角形五例现在均失败。但对原 CX-29 单页分别只做以下变异，`inspect_dxf` 仍全部接受（见 `readback-mutations.json` 和 `mutations/`）：

| 变异 | 实际错误 |
| --- | --- |
| DIMENSION override `dimlfac=10` 并重生成尺寸块 | 几何 25，显示尺寸变为 250 |
| viewport `view_twist_angle=45` | 纸面视图旋转 45° |
| layout `paper_width=420` | 目标 A4 纸宽漂移为 A3 宽 |
| TEXT `halign=2` | 文字改为右对齐，锚点/占位变化 |
| 删除所有 FRAME/FRAME_YELLOW 实体 | 整个图框消失 |

另在隔离候选副本将 CX-26 单页 PDF 替换成 CX-29 PDF，仅更新该副本 manifest 的正确字节 hash，保持 DXF/页面规划不变；实际 `probe_formats.py` **退出 0/passed**。CX-26 交付页因此可显示 25/23.52 等错误内容而通过。见 `wrong-pdf-validation.log`、`wrong-pdf-manifest.json`、`wrong-pdf-validation/`。冻结原候选未被替换；其正确单页/汇总关系已独立核实。

修复验收：补足真实显示尺寸倍率/样式、纸型/视口旋转和裁切、文字对齐与字形、受控图框线条的检查；PDF 需逐页核对内容与 DXF/规划，不能只核 hash 和字体名。五个新 DXF 反例和错误 PDF 必须失败，原三页正例仍通过。本项限 B02 样件承诺，不要求提前实现 B04 完整排版。

### F06（高）：空壳 CAD 记录仍可放行，延期 runner 仍不可完成

位置：`scripts/check_format_gate.py:48`、`:77`，`scripts/probe_formats.py:50`，`scripts/acceptance_registry.json:81`。

独立构造带当前产物 hash 的隔离负例：`target_cad` 填 AutoCAD/2018/`edit_save_reopen=true`，`evidence_hashes` 仅指向现有 **synthetic fixture JSON**，完全没有 CAD 操作人、操作时间、编辑/保存/重开步骤、输入输出或截图。`validate_approval` 返回 **[]**。将 DWG 决定时间写成 **2099-01-01**，`validate_decision` 也返回 **[]**。空批准和错误产物 hash 现在被拒绝，属于有效的部分修复，不能据此认为完整 CAD 证据已被验证。

使用上述明确标为反例的假批准、正确绑定的延期决定和隔离 registry，完整注册 B02 runner 的 gate 与 human gate 均显示 passed，但 runner **仍退出 2，唯一剩余阻塞为必需 DWG probe**。`probe_dwg` 仍无条件 `return 2`，因此未来即使用户真实同意延期也无法走通既定路径。详见 `runner-postpone-counterexample/`，这些记录绝不作为签收。

修复验收：CAD 证据必须结构化绑定本次确切输入、操作人/时间/版本、编辑保存重开动作、输出及可核查佐证，拒绝无关文件和不合理时间。延期决策与 runner 的 required 规则应一致：保留“未转换/blocked”事实，但在真实有效延期时政策门槛可以满足；DWG 首版必需分支必须要求真实授权正反转及 CAD 编辑证据。独立合成正反分支应覆盖完整 runner，不能仅测试 `validate_decision`。

### F09（中）：假正反转仍被称为 verified

位置：`drawing/dwg_adapter.py:38`、`:64`。

隔离记录的 input 是 `not a DXF`，DWG 是 `AC1032` 加 64 个 x，roundtrip 是 `not a DXF either`。三者 hash 正确，配任意普通 Python 可执行文件和项目评估授权字段，即返回 **verified_evaluation_only**。helper 也接受新生成的 header-only 垃圾。检查文件头/hash 不等于验证 DXF→DWG→DXF 的语义或证明指定转换器实际执行过。见 `synthetic-roundtrip-input.json`、`results.json`、`dwg-counterexamples.json`。

普通垃圾、已存在旧输出均被拒；实际非零退出 7 被拒，Linux 超时后子进程未存活，确认这些修复有效。初次 failure 负例字符串替换意外产生 SyntaxError/退出 1，已在 `supplement-results.json` 以正确独立程序补测退出 7；未把前者误报为退出 7。失败只在异常中保留最后 500 字 stderr，stdout/超时 stdout+stderr 没有完整持久化，仍不满足可追溯失败日志要求。

修复验收：授权可用保持 available_unverified，只有确切转换器/命令/版本/输入输出/完整日志绑定及真实格式、语义正反转核验后才升级 verified。失败和超时也应留完整日志；保留已有垃圾/旧输出/进程组回归。无需且不得为修此项擅自运行 ODA 或使用其他项目许可。

## B01 结论适用性与本轮影响验证

唯一已接受的历史 B01 仍为 `docs/evidence/B01-fix-2-r2/summary.json`，SHA-256 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。历史报告及日志/输入/产物绑定核验有效，其旧源码指纹不被自动认作当前源码 PASS。

本轮在干净独立快照运行未改动的 B01 runner：contract **53 passed**、runner **31 passed**、ECMAScript 契约和 wheel 隔离安装均退出 **0**，fixture、Schema、OpenAPI、wheel 静态检查均通过。总结果仍是 **2/blocked**，原因是 registry 引用的历史 boundary evidence 不匹配当前源码指纹。初次快照漏复制项目本地 `.tools/uv` 导致 wheel 也 blocked；随后复制同 hash 的本项目工具重跑，`b01-complete/` 为完整结果，初次结果保留不覆盖。

本轮另在原远端工作区只读取得真实 before/after 外部源快照，针对当前指纹调用同一 `validate_boundary_evidence`，得到 **source-boundary passed / valid comparison; unchanged**；不是伪造、复用旧采样或回写外部源。`boundary-validation.json` 是单项检查载体，初始总 status=blocked 不被冒充完整 B01 PASS。本轮所需 B01 影响验证已有新证据，但默认 registry 的陈旧路径仍需执行器在最终修复后刷新并真实重跑；修改 registry 会改变源码指纹，采样须在最终配置后取得。复审不代改 registry 或历史结论。

## 真实外部门槛与交接

技术缺陷修复并重新冻结后，仍必须由具名工程审阅人在 AutoCAD 2018 或用户明确批准的目标 CAD 对确切 DXF 编辑轮廓、文字和原生尺寸，更新尺寸、保存重开，记录版本、人员、时间、前后 hash、截图及结论。当前未提供此实测，ezdxf/PDF 度量不能替代。模板重排、SC 字体替代、引线 5/10/10 mm 均仍待工程批准，DWG 首版延期/升级仍待用户基于最终新证据决定；复审不代签。

本轮只提交本报告、原报告归档和 `docs/evidence/B02-rereview-1/`。保护清单核验原业务/测试/执行报告/冻结候选/state.json 未改变；双端新证据逐文件 hash 一致。提交及清洁状态记录于同目录 `git-handoff.json`；该记录在内容提交后单独提交，最终 HEAD 以两端 `git log -1` 为准。完成后停止在 B02。
