# B02 第十一轮修正独立复审

结论：**本轮技术复审 FAIL，技术必须修复项 3（均 P2）。** 原生模板恢复、Excel 映射、真实毫米几何和原生尺寸再生成已取得有效进展，但字段替换丢失 MTEXT 原格式、MTEXT 有效显示校验存在绕过、PDF 对同字体尺寸文字额外缩小至 80%，尚不能认定技术闭环。此结论来自实际源码、冻结图面和独立反例，**不是因为本轮未指定审批人员**。

产品首发范围已按用户真实决定保持 **DXF/PDF，DWG 延期**。这项决定已完成；一次性源模板 DWG→DXF 是模板准备，二者分开。正式具名工程审批留交付前，本轮技术审查已继续完成。

仅写本报告、第十轮原字节归档 [B02-rereview-10.md](B02-rereview-10.md) 和新证据 docs/evidence/B02-rereview-11/。归档 SHA-256：d44bcf5eff566e93c5b2439c730f9337429445b4e06c2e2beae07ead32be95a7。未修改业务、既有测试、旧证据、执行报告、冻结候选、registry、决定、模板或 orchestration；未启动后续批次、新聊天、子代理；复审者未运行真实 converter、ODA 或目标 CAD，未创建真实批准。

## 身份与审查范围

本地交付 1f4ef9e2880265bef84d1abe628d40022522da9f；实际复审起点为其后仅追加调度的 6b3aa8ec6edaa1cbcb387a59d642c4ef81366e5e。远端起点 80b6e1ad07e01542f2d6df4aa7cb2628237ee60b。两端在创建复审目录前 clean，分支均 codex/b01-foundation，无适用 AGENTS。源码契约一致：

**e241d2e312de1f968ee32fc9762fa744ee9a90e2e9cbd16a6124a9964527d675**

已读取 plan、B02、C02/C05/C06/C07、相关需求、B01 有效独立认可、上一轮复审、当前执行报告、CAD 调查、真实用户审阅、中文局部对照、审批契约/生成器/gate、registry、模板刷新/加载、writer、renderer、readback、probe 和相关测试变化。完整实现 diff 保存在 local-implementation-diff.log 与 implementation-diff.log。默认 runner 使用新鲜快照 /tmp/heater-b02-rereview11-1ks_7_69/snapshot；依赖和生成器另建新鲜快照，未只消费执行方结果。

| 冻结对象 | 独立核对 SHA-256 |
| --- | --- |
| 用户真实审阅 | 574cadef4e53e284f099bcffe1cdb8bf4d3fc091cd2c00245d4de114cc31f915 |
| candidate manifest | ed985c282f179212acf8a2d2796c502051548c7a9cb55d09acefdd5f35df3c01 |
| template manifest | eb1037809bda442a80ea75a89d8f08d5df5da0c432de2181ebfcacf35136abf0 |
| layout | c3e2e9cc1606fd94ef7b32fba92356c23107c52acfd175bb8cf147dc85124bce |
| font profile | cb415c1f379b023d52311b6466c88bae31f9b9cfc3938bf316b105ebcfaab114 |
| 原始转换 DXF | 9bcca3259ef7881af10e640538ec9cd8947bce7d86ee30f18e0c20f7cc8b4c15 |
| 受控 template.dxf | 3bcf858e7417f304bcaf7100abc1b8fa111dad76a070337f790b687edf5415c7 |
| 汇总 DXF | 6ca4af337480c15f43900fdb2534bcb27afe6206685c83464c75065512583143 |
| 汇总 PDF | 8f6de7a00c10f9734dd846ab2ac6734b5bf82bcdfd78f8553f902a86bdd17dad |
| 28 页差异 PDF | 6dd4022fc31b4e87b76923affc8332d0a79987cf2c8e96de56874e350d0c3645 |
| 当前 pending 人工记录 | 3fb16601c4d82e0ae8d2ad14e0fa8e973a230a136e8e882733ea8af72825be77 |

两端 candidate/probe/template/human 的实际 artifact hash 均匹配；其余最终对象身份见 [pending-boundary-review.json](../evidence/B02-rereview-11/pending-boundary-review.json)。本轮保留 30 份完整独立 probe 输入，逐项核对 420 个 manifest artifact hash，无不匹配；负例未重渲染成功的 PDF 均如实标注，未冒充新结果。

## 必须修复 1：填字段时保留原生 MTEXT 段落与内联格式（P2）

位置：service/src/heater_drawing/drawing/dxf_writer.py 的 _add_native_template()，当前对全部 MTEXT 直接执行 entity.text = value。源实体原本含居中段落指令，例如型号为“\\pxqc;型号名称”，单位为“\\pxqc;{\\H1.042x;单位名称}”；candidate 被写成纯文字。插入点、attachment 和名义字高相同不能证明有效文字布局相同。

独立对三页全部相关字段，用两侧同一个锁定 Noto 字体比较“保留原格式后替换占位值”和实际 candidate，排除了 SHX 不可解析的影响。第一页面的型号 CX-29，实际字形左边约 x=95.753 mm，保留原居中格式则约 x=112.712 mm，相差约 16.958 mm。三页完整图和局部标题栏也可见型号、代号等靠左。单位/名称原有 1.042x 局部字高同样被去掉；这里是文字自身格式，不能与禁止整体放大 Excel 几何混为一谈。

要求：以原实体为准安全替换占位值，保留段落对齐、内联字高/宽度、行距及有效锚点；技术要求文字若确需改格式，单独明确受控规则。补验证实际 raw/effective format 和可见位置，不能仅比较 plain_text、insert、attachment。证据：[native-text-review.json](../evidence/B02-rereview-11/native-text-review.json) 的 native_formatting（33 个字段记录）及 native_text_review.py。

## 必须修复 2：重新约束 MTEXT 有效显示，并恢复实际字形边界检查（P2）

位置：readback.py 的 _validate_texts() 只比较 MTEXT plain_text、char_height、width、attachment、line_spacing_factor 等，未锁定其内联格式或 flow_direction。原字形 cell/paper 边界、框线穿越、文字相互碰撞检查同时被撤成仅检查插入点在纸内；complete_content_box 也把文字当成零面积点。单页/汇总签名因此同样漏掉这些属性。renderer 会解析部分内联格式，却将可见文字始终画成黑色。

本轮从最终冻结 candidate 派生四个反例，三份单页与汇总 DXF 同步修改设计人员 MTEXT，真实重建全部三页 PDF/PNG 和汇总 PDF，刷新且核对 manifest 全量 hash，再运行完整 probe：

| 受控字段实际变异 | 单页与汇总 readback | 实际 PDF 重建 | 完整 probe |
| --- | --- | --- | --- |
| 内联字高 \\H3x; | 全部接受 | 成功 | 0 / passed |
| 内联字宽 \\W3; | 全部接受 | 成功 | 0 / passed |
| 内联红色 \\C1; | 全部接受 | 成功 | 0 / passed |
| flow_direction=3（top-to-bottom） | 全部接受 | 成功 | 0 / passed |

前两项改变有效字形范围；已目视反例实际重建图，3x 字高的“陈黎”跨越设计/校对行并覆盖“曹运涛”，仍完整 probe 0。颜色项在 DXF 中指定红色但 PDF 仍画黑色；方向项没有被受控语义校验覆盖。这里的 passed 是漏洞复现结果，不能作为候选合格证据。同批 mixed-case Continuous 合理正例完整 probe 0，未把全部 MTEXT 或合理显式默认一概拒绝。

要求：基于来源模板建立安全、明确的 MTEXT 格式规则，验证实际使用的内联/段落格式和有效方向；单页/汇总签名纳入有效显示属性；用实际布局后的字形检查纸面/单元格/框线/文字碰撞。不能用删除格式或只看插入点规避检查。完整输入、命令、退出码、重新生成的 PDF 与日志在 [native-text/](../evidence/B02-rereview-11/native-text/) 和 native-text-review.json。

## 必须修复 3：移除对同字体原生尺寸的 PDF 额外 0.8 缩放（P2）

位置：pdf_renderer.py 的 _draw_editable_text() 在生成可见 CAD glyph path 前，对所有文字统一乘 fonts.json 的 pdf_text_scale=0.8，连原生 DIMENSION 缓存展开的 HEATER_CJK 文字也缩小。该尺寸样式已经引用与 PDF 完全相同的 NotoSansCJKsc-Regular.otf，SHA-256 e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322；这部分不涉及 HZ/SHX 替代。

独立测量六个尺寸的原生缓存字形，又直接从冻结 PDF 的可见矢量 fill 取实际边界。六处实际宽、高比均约 0.8，与额外缩放预测最大边误差仅 0.000012083 mm。尺寸缓存 char_height 为 3.5/7 model mm（对应纸面 3.5 mm），PDF 使用的名义字高则为纸面 2.8 mm。尺寸数值、几何和箭头没有因此改变，但 DXF/PDF 的实际字形大小与相对位置已不一致。现有 probe 把同一个缩放 renderer 的输出当 canonical，不能独立发现这种偏差。

要求：同一真实字体的原生尺寸按其原生高度和定位渲染；HZ→Noto 临时外观方案如确需补偿，必须限定到确切文字类别并明确依据，不能全局缩小尺寸来获得可见候选。修复后用原生缓存与实际 PDF 可见矢量独立比较。证据：[pdf-scale-check.json](../evidence/B02-rereview-11/pdf-scale-check.json)、pdf_scale_check.py 和 native-text-review.json 的 dimension_pdf_scale。

## 本轮已核实的修正与独立验证

原始转换 DXF→受控 template.dxf 的 78 个模型实体已逐个比较有效 DXF 属性：45 LINE、19 MTEXT、14 TEXT，只有平移 [-2826.401843915681, 4438.726129851452, 0]，无几何缩放。原图层、原文字样式、原 dimstyle 有效属性保留；HZ=txt.shx+hzdx.shx、width=0.7。“DIM”在原模板是文字样式名称，不应误读成尺寸样式名称。标题栏/会签栏、设计/校对/审核/空工艺行、标审/批准、阶段/质量/比例分格及黑黄线结构得到恢复；字段最终格式仍须修复上述第 1 项。

原 PDF 与原生模板约 1.042 的映射关系没有复制到 Excel 几何。三页保持 25×25、30×50、100×300 mm 与 1:1、1:1、1:2。图形中心、标注侧别和引线已按样例分别还原；纸面引线间距约 5.3018/9.9942/15.0015 mm，并有逐页 inside/outside 值；非样例 fallback 为 10/10/10、中心 (88,187)、尺寸偏移 8 mm/auto。它们仍是从 PDF 逆推的还原候选，不是原模板中发现的源设计规则；“导线长度300mm”仍只作工艺文字。

独立读取 Excel A:Q 三行全部 51 个字段，与 fixture 和冻结 DXF 读回核对一致。人员职责分别为：

| 页 / Excel 行 | 设计 | 校对 | 审核 | 标审 | 批准 | 数量原文 |
| --- | --- | --- | --- | --- | --- | --- |
| CX-29 / 2 | 陈黎 | 曹运涛 | 王岩峰 | 郑玲 | 施蓉蓉 | 18片 |
| CX-26 / 3 | 吕鑫 | 王岩峰 | 曹运涛 | 郑玲 | 周苗苗 | 12（备份2） |
| KX-11 / 4 | 吴立 | 曹运涛 | 郑玲 | 陈黎 | 周苗苗 | 76片（备份13片） |

第二页以 Excel O3“郑玲”为权威，没有复制旧 PDF 的“陈黎”。电阻/偏差为 23.52±0.71、58.8±1.76、200±6 Ω，型号、名称、单位、阶段和比例均逐项核对。见 [excel-field-check.json](../evidence/B02-rereview-11/excel-field-check.json) 和 local-provenance.json。

| 独立检查 | 实际结果与边界 |
| --- | --- |
| 默认原注册 B01 | 0 / passed；53 contract + 47 planning，0 skip，Node/wheel 和 10 checks 通过 |
| 默认原注册 B02 | 2 / blocked；120 format（179.33 s）+ 220 regression（195.65 s），0 skip；正常 probe 0，现有技术 checks passed；人工及 format gate pending，产品 DWG 探测 2 符合延期策略 |
| Windows | 220 passed、0 skip（232.82 s）；timestamp 另五次均 0；精确冻结候选完整 probe 0、candidate/template immutable；改名 Python 被 Authenticode 身份检查拒绝，未执行改名程序 |
| 尺寸线型来源完整矩阵 | 6 个 style/override 显式 Continuous 正例 + 3 对照均真实重新生成四份 DXF、重建三页 PDF/PNG/汇总 PDF，probe 0；6 个非 profile 来源反例均 probe 1 |
| Continuous 缓存分支 | 10 个完整负例均 readback/renderer 拒绝、probe 1，涵盖颜色/图层/线宽/truecolor/透明/ltscale、嵌套/顶层越界、定义虚线、来源虚线而缓存连续 |
| 新原生框线/文字边界 | 31 个负例 readback 拒绝；显示属性负例 renderer 也拒绝；3 个显式默认 + 原 Continuous 的大小写变化共 4 个正例通过。语义位置/tag/样式依赖由 readback 负责 |
| 尺寸更新 | 6 个原生尺寸重复 render、保存、重开稳定；真实定义点 +5/+7 mm 后测量/文字正确，保存重开再 render 稳定；仅 ezdxf 软件实测，不冒充 AutoCAD |
| 实际 CLI fixture | 六项真实 verify_batch/check_format_gate 子进程退出 0,2,1,1,1,0；fixture 在 pytest 临时目录，非活跃批准 |
| B01 依赖 / runner | 当前精确 report/binding 正例通过，12 删除/伪造/重绑/时效/hash 负例阻断；旧 fix-3 probe 中毒不影响当前证据；路径形状反例拒绝 |
| Runtime provenance | 普通 Python helper 正例/恢复正例通过；retained token 深层变异、导入、跨调用、版本/descriptor/stdout/stderr、真实同尺寸改字节、删除/原子替换/目录替换均拒绝；非 converter/CAD 实测 |
| C02 / 差异表 | 三 DrawingPage 语义验证通过；28 页差异表 415 行、2658 cells、44231 可见 glyph，显示内容匹配、violations=[] |
| 新 MTEXT 显示矩阵 | 4 反例完整 probe 错误通过 + 1 合理正例通过，构成上文技术发现，不计为修复成功 |

30 份完整候选的 hash 检查见 [review-facts.json](../evidence/B02-rereview-11/review-facts.json)；具体来源/缓存矩阵分别见 dimension-source-review.json、continuous-branch-review.json；新原生显示检查见 native-display-review.json。辅助脚本初次默认属性、DIM 名称、调度起点和混合大小写选取错误的诊断日志保留，均已修正并以实际输入重验，未把复审 harness 错误报为产品缺陷。差异表目前还把 outer 四边与 frame 内相同边重复列入，部分匹配记录冗余；其排版验证通过不等于差异已获工程认可，后续可清理重复项并刷新明细。

已目视原三页、候选三页、全部三张中文局部对照和覆盖差异表 28 页的七张 contact sheet。中文字/技术要求/箭头可辨，工艺空行与职责分格已恢复；标题栏靠左和尺寸文字缩小属于上述技术发现。目视记录见 [visual-review.md](../evidence/B02-rereview-11/visual-review.md)。

## 模板转换、字体与审批边界

独立核对 5090 PATH、包清单和实际缓存，没有可用的 AutoCAD 2018/BricsCAD 等目标 CAD 证据。执行者为本项目独立官方下载的 ODA File Converter 27.10.0.0 缓存实物、下载 headers、输入/输出、exit 和空 stdout/stderr 均核对。AppImage SHA a73eea1dfc873cd46b94bfa07760dcff0082c4300dd33c5401e8a526cfab787b，实际 exe SHA 03a219a6148852e7c8e5f7297a1c4c2e1cc992277580acc6111507ada342e6a8。相同官方版本 hash 不表示复用了另一项目实例。

另从执行者真实聊天的 commandExecution 只读恢复了未截断的下载/解包及唯一转换命令、exit=0 和输出：包含 timeout 120、xvfb-run -a、三个 ODA 库/插件环境路径、ACAD2018 DXF 0 0 "*.dwg"。见 [oda-executor-history.json](../evidence/B02-rereview-11/oda-executor-history.json)。它补充了缓存缺少独立 argv 文件的记录缺口；不声称已持久记录整个继承环境。复审未发消息给执行者，也未重跑转换。

本轮重新读取官方 free application/运行说明及实际二进制禁止未经同意分发条款，核对独立下载路径与本次一次性模板用途，未将其推论为 SDK、服务器生产、产品 DWG 或再分发许可。工具/字体二进制未加入复审交付。原 HZDX SHA 42a8be6684d58bd2d886d7670d676af9445d65ca208ff116e8103b9114ed5f9c；实际 ezdxf 1.4.5 报 UnsupportedShapeFile: BIGFONT shapes are not supported yet，只证明当前库限制。合法 CAD 链能否正确显示/出 PDF 仍待真实验证；未知再分发权不等于受控使用必然不可行。

当前 pending 人工记录与 candidate/template/layout/font/face 精确绑定，scope 和十项动作与共享契约/gate/生成器一致；人员、角色、时间、结论为空，动作全 false。真实新鲜 clone 调用生成器成功，payload 完全相等；生成文件 SHA 365fa6731445249e95f0886f7a0eac30d98fc62a198d800de0c2c05fb1afad6b，与 active pending 仅 CRLF/LF 字节差异，保留各自真实 hash，未擅自重写或标批准。审批 shape/hash 反例均被拒绝。

后续真实操作由操作人保留文件、截图与实际动作事实，再由工具计算 hash、整理待核对结构化记录；普通用户无需手填复杂 JSON/hash。现有生成器只生成 pending 模板，未宣称能自动完成实际操作证据或工程批准。

## C07、orchestration 与原文件保护

当前 registry 登记的 fix-11 before/after 通过严格 shape、baseline、源码、稳定 hash 和时效检查，独立重算 unchanged；本轮独立采样窗口也经原 validator 通过。历史 fix-7 observation 与历史 baseline 重算仍为 changes_observed/unknown_external，未重绑成当前输入，也不要求整个跨批次期间外部工程永远不变。详见 pending-boundary-review.json、boundary-validation.json。本轮未写入/回滚外部项目。

本地交付 1f4ef9e 的四个 orchestration 文件与自身 fc7ef4c 起点 blob 一致；当前 state/events 的变化来自后续 6b3aa8e 调度，不能误报实施者破坏。远端 517ea7f 曾误写 state/events，43470b1 已恢复为远端自身 4cf5630 的原字节；四文件一致。恢复前后冻结技术输入 hash 和源码指纹未变，无须为纯文档恢复机械重复全量回归。本轮两端均与各自 review-start 原文件基线核对。

本地 8748、远端 8740 个原文件分别逐字节保护，源码条目相同；保留本地既有额外日志/runtime、远端根 .gitattributes 和各自 orchestration 差异。最终保护及 mirror 见 local-protection-final.json、remote-protection-final.json、source-mirror.json。证据索引绑定最新报告、精确第十轮归档和本轮新材料，排除自身及其后单独提交的 Git handoff。两端分别限定暂存路径，核对工作文件/暂存/提交 blob、diff --check 和 clean；内容提交及检查见 [git-handoff.json](../evidence/B02-rereview-11/git-handoff.json)。

## 当前样件与四类后续事项

当前 [三页 PDF](../evidence/B02-fix-11/candidate/heater-sample.pdf)、[可编辑 DXF](../evidence/B02-fix-11/candidate/heater-sample.dxf)、[中文局部对照](../evidence/B02-fix-11/localized-comparison.zh-CN.md) 和 [28 页机器差异 PDF](../evidence/B02-fix-11/candidate/reference-difference.pdf) 是本次被审样件，**包含已指出的缺陷，尚非可交付批准版本**。

1. **本轮技术修正：** 修复上述三个 P2，再更新候选、manifest、pending 绑定及相应真实正反例；不得仅凭现有 220 项通过撤销发现。
2. **外观/工艺待确认：** 原生黑黄线/分格映射、HZ 与临时 Noto 外观、修复后的有效文字布局、三页还原参数及非样例 fallback；不要求用户无差别批准全部 unknown。
3. **目标 CAD 待验证：** 在真实合法环境对精确修复候选执行打开、编辑轮廓/文字/原生尺寸、显式更新尺寸、REGEN、保存、关闭、重开，记录真实产品/版本/人员/时间/输入输出和截图；软件 render 不代替此项。
4. **交付前正式门槛：** 技术修正和真实 CAD 事实完成后，再由具名工程人员对最终精确版本作正式判断；当前无需因人员未指定而停止修正。DWG 产品延期已完成，不再列为缺失决定；若未来另行升级产品 DWG 范围，再单独满足对应授权和真实验证。

**本次停在 B02，不进入后续批次。**
