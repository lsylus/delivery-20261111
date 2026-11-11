# B02 第十轮修复独立复审

结论：**技术闭环可送人工；技术必须修复项 0。总体仍为 FAIL。** 上轮显式 Continuous 来源真实重生成后被 renderer／完整 probe 错误拒绝的 P2 已关闭；本轮未发现新的技术必须修复项。真实 AutoCAD 2018 操作、具名工程审批和 DWG 首发范围决定仍缺失，不能据本报告把 B02 标为 PASS。

仅写本报告、第九轮原字节归档 [B02-rereview-9.md](B02-rereview-9.md) 和新证据 `docs/evidence/B02-rereview-10/`。归档 SHA-256：`00111b85d6251224517bdab1aa011d8e075ed8b007af0dfb342119d77151ba9a`。未修改业务、既有测试／证据／执行报告、冻结候选、决定、registry、模板或两端 orchestration。未启动后续批次、新聊天或子代理；未运行真实 CAD、converter、ODA 或 DWG，未借许可、未代签。

## 身份与实际输入

用户交接本地 `b098b293d54b890535a47d6fee14a91fe7ed023c`；实际开始为仅追加调度文档的 `452af4c751573cf0b497972d2ee0a6c5ea765904`。远端 `96c01cc7f567e6b9c27f2556e1547e7294b10870`。两端初始 clean，分支 `codex/b01-foundation`，无适用祖先或子目录 AGENTS。源码契约一致：**`0d531cbcbc5a4b7466447fdc06b6b2bd21bfcd738a58691caf63aa970a228a97`**。

已核对 plan、B02、C02/C05/C06/C07、相关需求、基线／progress、B01 独立认可、上轮复审、当前执行报告／决定；读取完整显示约束、renderer 递归前置检查、readback／probe、审批契约／生成器／gate、registry 和执行方新尺寸审计。独立保存本地 `d62d264..HEAD`、远端 `228644c..HEAD` 的实现 diff。实质改动是在受控尺寸缓存的非嵌套 LINE 中接受显式 Continuous；其余显示约束仍在。

默认 runner 使用独立新鲜快照 `/tmp/heater-b02-rereview10-nv6_gxzd/snapshot`；显示矩阵另建新鲜快照。所有新候选从最终 `B02-fix-10/candidate/` 派生。逐项核对执行方 6 正例和 3 对照的实际输入、manifest、产物、probe 及日志 hash，未只依赖审计中的布尔值。

| 最终对象 | 独立核对 SHA-256 |
| --- | --- |
| candidate manifest | `3c256c5b62035419f0d5ddb3c2b0941a5278d272d1864a78305da691f27950a8` |
| template manifest | `d09902d603ae6f2b2867793377d723d9d3620891f02eacbeb0192ac293a67244` |
| 汇总 DXF | `b5661044a32ceb82c26c80c2fc30a62595c0278fcdb2c03ea3fc6c28d957e59b` |
| 汇总 PDF | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| reference-difference.pdf | `b7275feebadf143f932625af6beea55bfdc9ff1b2ea7edac69ab6e39300895c3` |
| executor 最终 validation | `a9a7636c4b83ea6112bef935ebb13c99cb43bfd1e87369b6d338faed2dbccd22` |
| executor Windows validation | `210826befeb6eab51a803d9d6ea2943f3e4dbb0ecd023329c3431218a2ef9eee` |
| executor dimension-continuous-audit | `25ff3f52e21d7ecb4f46386862c94c0657346dcba321216ec3197056be27699e` |
| 当前 pending human record | `c308e3491a36df45a6ca44157e2b4f2220e8ea2740607b8b27a4ea5656e2dda6` |

candidate／human／probe 的全部 artifact hash 均匹配实际文件，candidate 与模板和新鲜快照逐文件相等；正常双平台 probe 均 immutable。其余最终 runner、boundary、capability、gate hash 见 [pending-boundary-review.json](../evidence/B02-rereview-10/pending-boundary-review.json)。第九次执行报告原归档 hash 为 `fcbc47e61aa503490fe0a8ea5494a01fde94396fea947ea6dbaa8706110ee553`。

## 上轮 P2 关闭：真实 Continuous 正向全链路

修复位置 `service/src/heater_drawing/drawing/display_profile.py:265`：仅在 `dimension_cache=True`、实体类型 LINE、`block_child=False` 时增加 Continuous 许可；嵌套 LINE 仍需 BYBLOCK，顶层仍需 BYLAYER。实际 Continuous 定义、受控层、真实尺寸 style／override 来源在展开缓存前独立校验。颜色 0、图层 0、线宽 -1 及其他显示属性约束未放松。

独立为三个 style 字段及三个保留原 override 的实体字段建立**三单页加汇总全部一致**的完整候选。每一份文档均对全部尺寸调用真实 `DIMENSION.render()`，保存、重新读取、audit，检查实际 style／override／测量／缓存 LINE，并用独立 RenderContext 解析线型。之后实际重建三页 PDF／PNG 和汇总 PDF、刷新全量 manifest，再执行真实完整 probe。

| 独立完整候选 | 三单页／汇总 readback 与签名 | 实际 PDF 重建 | 完整 probe |
| --- | --- | --- | --- |
| `positive-style-dimltype` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `positive-style-dimltex1` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `positive-style-dimltex2` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `positive-override-dimltype` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `positive-override-dimltex1` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `positive-override-dimltex2` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `control-omitted` | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `control-noise`（Continuous 3e-14） | 接受，全部一致 | 三页及汇总成功 | 0／passed |
| `control-unused`（未引用虚线表项） | 接受，全部一致 | 三页及汇总成功 | 0／passed |

每例含四份重新打开的 DXF、共 12 个尺寸实例，audit 均 0 errors／0 fixes；测量和完整 overrides 在保存重开前后一致。六正例每份文档均实际产生 Continuous 缓存 LINE，实际解析 pattern 全为 `[]`；全部单页／汇总 page signatures 相等，probe 均确认 candidate/template immutable。完整输入、前后实体属性、真实渲染 hash、命令／退出码／日志见 [dimension-source-review.json](../evidence/B02-rereview-10/dimension-source-review.json) 和 `dimension-source-cases/`。

对应六个越界来源负例（style／保留 override × dimltype／dimltex1／dimltex2，真实 REVIEW_DASHED）在三页与汇总 readback、renderer、完整 probe 均拒绝，probe 均 1。负例另对实际第一页重生成保存重开后再次 readback／render，仍拒绝。没有以旧缓存画面连续掩盖虚线来源。

新增 [continuous-branch-review.json](../evidence/B02-rereview-10/continuous-branch-review.json) 明确选中 `linetype=Continuous` 的缓存 LINE，十个完整反例全部 readback／renderer 拒绝、probe 1：颜色 2、错误图层、线宽 25、truecolor、透明度、ltscale 2、嵌套箭头 LINE Continuous、实际 Continuous 定义虚线、虚线来源但现有 Continuous 缓存、顶层 LINE 显式 Continuous。角色 helper 同时确认直接缓存接受、嵌套／顶层拒绝。

首组十个边界实验选中默认 BYLAYER 缓存 LINE，不能直接证明新分支；其输入／日志完整保留为 `continuous-boundary-*`，仅作为继承约束补充，未冒充新分支验证。后补十例均断言实际选中实体为 Continuous。负例复制来的 PDF 明确未成功重渲染。

## 独立回归、审批契约与图面

| 检查 | 本轮实际结果 |
| --- | --- |
| 默认原注册 B01 | 0／passed，53 contract + 47 planning，0 skip，10 checks、Node／wheel 通过 |
| 默认原注册 B02 | 2／blocked；110 format（159.82 s）+ 210 regression（173.99 s），0 skip；正常 probe 0，技术 checks passed；仅 human-gate-0／check-format-gate 阻塞 |
| Windows | 210 passed，0 skip，204.00 s；timestamp 另五次均 0；最终冻结候选独立 probe 0、immutable |
| 显示矩阵 | 54 组件、39 完整 probe：34 负例 1、5 正例 0；五正例三页 PDF／PNG 及汇总 PDF 均真实重建 |
| 合理对照／显示反例 | 3e-14 几何噪声、显式默认、Continuous 定义默认／噪声、未引用表项均通过；实际虚线／complex 定义、父尺寸、图层、缓存、INSERT、嵌套与组合异常均拒绝 |
| 旧语义／PDF／颜色 | 24 DXF 异常拒绝；错误单页、单页横移、仅汇总第二页横移均完整 probe 1；黄色改黑／仅汇总改黑拒绝 |
| 实际 CLI fixture | 六项真实 check_format_gate／verify_batch 子进程退出 `0,2,1,1,1,0`，仅在 pytest 临时 fixture，非活跃批准 |
| B01 依赖／runner | 原注册 report／binding 正例通过，12 删除／伪造／重绑／时效／hash 负例阻断；旧 fix-3 probe 中毒不影响当前 built-in；路径形状反例拒绝 |
| runtime provenance | 普通 Python helper／恢复正例通过；retained-token 深层／导入／跨调用、版本、descriptor／stdout／stderr、同尺寸改写／删除／原子替换／目录替换拒绝；Windows 改名 Python 的 Authenticode 身份拒绝，未执行改名程序；未执行 converter |
| 字形／箭头／尺寸 | 129 文字、876 glyph、12 SOLID；最大 glyph 边误差 0.0000170093 mm、箭头 0.0000172347 mm；6 原生尺寸重复重生成保存重开稳定，定义点 +5/+7 mm 后测量／文字正确；再生成 glyph 误差 0，碰撞 0 |
| 字体 | 实际使用同一 NotoSansCJKsc-Regular，OTF SHA `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`；TTC face 2／OTF／系统包许可均核对，未用 fallback 测量 |
| C02／差异／直接签名 | 三 DrawingPage 结构／语义通过；单页和汇总各页 21 段框线端点／颜色对应；24 页差异表 349 行、2238 cells、34163 可见 glyph 通过；DXF 原字节副本签名相同，轮廓平移签名不同 |

当前待签的 candidate/template/layout/font profile/face 与实际冻结输入一致，五项 scope 和十项动作与共享审批契约、gate、生成器一致，registry human hash 匹配。scope／缺 regen／缺 close／额外动作及各身份 hash 反例均拒绝。真实新鲜克隆调用生成器，当前 pending 与生成输出 **bytes 和 payload 均完全相等**。人员、角色、时间、结论仍为空，动作全 false，没有写 approved 文件。

已目视检查三张完整候选、原三页 contact sheet 和差异表全部 24 页的六张 contact sheet。中文字、双引线、尺寸箭头、黄色框及标题栏可辨；第二页标审按 Excel 为“郑玲”。源图线位／字段重排和 SC 字体替代仍须工程确认，软件测量不替代目标 CAD 验收。

主命令／环境／源码身份见 `results.json`；回归见 `impact-results.json`／`windows-results.json`；综合断言见 [review-facts.json](../evidence/B02-rereview-10/review-facts.json)。归档 **79 个完整独立 probe 输入**（39 显示、5 PDF／颜色、15 来源与对照、10 默认缓存边界、10 明确 Continuous 分支边界），全部 manifest artifact hash 已核；另核对执行方 9 个实际正向输入，见 [probe-candidate-archive.json](../evidence/B02-rereview-10/probe-candidate-archive.json)。

独立 B02 dirty_files 如实包含隔离快照中前序生成的 `?? docs/evidence/B02-rereview10-b01-current/`，无源码修改。执行方最终 runner dirty_files=[]，B01 HEAD `8d4fee294bed22659d57bb75e28c0b5c3534d06e`、B02 HEAD `0c6180967cb126c224b54ec54463ce16f87118d6`。历史独立认可 B01 summary SHA 保持 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。

## C07 与原文件保护

实际读取当前 registry 登记 fix-10 before／after，核对完整 shape、当前源码、baseline、稳定 hash、24 小时时效并重算：passed／unchanged。before SHA `cb9384e28657ad86e09f062d609d9ceeb596ba90fdf5e95ef24e00fe8e7ae0c4`，after SHA `668d1b02e436376c16683dcc1aa4d23e64b429f997d9153a34079157f7cb2ad5`。本轮独立采样的 before／after 也通过原严格 validator，为 valid／unchanged；其 SHA 分别 `898280645f4d6e22a84fa50f95ebff4c04f60a2ddc856c3c22d1e621d2b2c3a9`、`b018b7566b7542948175257b98de17262da52088fcd6debfc8d7ac3d6a424e47`。每组只解释其实际采样窗口。

历史 `B02-fix-7/b01-boundary-post-run-observation.json` SHA `3e5ed8edee28586658c379b5cb53e649ee629453f0aab2ca0ba92bbe52b99d76` 与恢复 baseline 重算仍为 changes_observed／unknown_external；对应历史源码 `f532dc2529653cae02ad0bcc01996cdbf801495f97e9af3154ca672866c5b1b7`。未重绑为当前 fix-10，未要求整个期间外部项目永远不变，未写入或回滚外部项目。

本地 **7085**、远端 **7077** 个原文件分别逐字节保护，source entries 相同。本地九个既有日志／runtime 文件、远端根 .gitattributes、两端不同的 orchestration state/events 均原样保留。见 `local-protection-final.json`、`remote-protection-final.json`、`source-mirror.json`。证据索引绑定本报告、第九轮原字节归档及全部新证据，排除索引自身和随后单独提交的 Git handoff。双端各自提交，精确限定暂存路径，核对工作文件／暂存／提交 blob SHA、diff --check 及 clean；内容提交及检查见 [git-handoff.json](../evidence/B02-rereview-10/git-handoff.json)。

## 可直接交给人工的结果与停点

冻结 [DXF](../evidence/B02-fix-10/candidate/heater-sample.dxf)、[三页 PDF](../evidence/B02-fix-10/candidate/heater-sample.pdf)、[24 页差异 PDF](../evidence/B02-fix-10/candidate/reference-difference.pdf) 和完整 [人工验收交接包](../evidence/B02-rereview-10/human-review-pack.md) 可直接使用。交接包列出精确 hash、AutoCAD 2018 的十项真实编辑／更新／REGEN／保存／关闭／重开操作、具名身份与时间、输入输出文件、结构化 JSON 及截图要求，以及模板／黄色框／锚点／SC 替代／5/10/10 mm 引线和差异表决定。

当前已有可编辑基线的技术证据；下一步是完成上述精确候选的真人验收及审批。DWG 延期保持基线或升级首发范围仍须明确决定；升级后再满足本项目授权、真实正反转与确切 DWG 的目标 CAD 验收。**本次停在 B02，不进入后续批次。技术闭环可送人工不等于整体 PASS。**
