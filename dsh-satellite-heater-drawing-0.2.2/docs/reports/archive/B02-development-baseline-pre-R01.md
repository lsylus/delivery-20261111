# B02 开发基线调整与宿主 FreeCAD 实测报告

记录日：2026-11-09（Asia/Shanghai）。本轮是实现报告，**不是独立审查或加工交付批准**。用户接受fix-12外观及当前PDF字体为开发方向，具名审批留交付前。当前执行者完成B02后交由调度独立审查；用户最新授权在独立技术验收通过且满足后批依赖后继续推进，不再要求整个项目停B02。

## 已通过项

- 技术要求整块纸面右移3mm、上移8mm；三页锁定字体字形实测右纸边余量15.148mm、右内框余量5.386mm，底部距标题栏顶部8.068–8.121mm。300mm导线文字不变，原template.dxf及fix-12原候选未改。
- 最终三页及汇总DXF/PDF的只读probe为passed，原生尺寸值为25/25、30/50、100/300mm，R2018/AC1032、INSUNITS=4；三页均保留33个可编辑TEXT/MTEXT和2个顶层原生DIMENSION，完整字形、图框、比例、布局和尺寸缓存受控。`validation/probe-result.json`绑定确切文件哈希。
- 统一引线规则short-edge-paper-v1已实现；11组实际DXF矩阵9组通过、2组按预期拒绝。覆盖小/大尺寸、短/长边及正方形、比例1:1/1:2/1:5/1:10、小数尺寸和同纸面尺寸不变性。极小0.5×1mm纸面因最小间隙0.1mm被拒绝，150×300mm纸面超框被拒绝；不再把planned passed当实际验收。
- 5090已装FreeCAD 0.19.2命令行原生运行：三页精确DXF副本均实际打开、编辑四条轮廓边使宽度+5mm、编辑名称追加-B02EDIT、重算检查尺寸行为、显式更新宽度尺寸，再分别保存/关闭/重开FCStd和导出的DXF。FCStd重开后轮廓、文字及显式更新的尺寸仍在；这项通过仅限FCStd模型编辑保存。
- 三页PDF由Poppler重渲染并逐页目视核对。开发gate和delivery gate已分开，开发可完成、正式交付pending、AutoCAD未验证、DWG延期不变。

## 统一确定规则与边界

令S=min(真实宽,真实长)/比例分母，结果均为纸面mm：

| 参数 | 规则 | 三页结果（按页序） |
|---|---|---|
| 双引线中心距 | min(12, max(2, 0.25S), 0.60S) | 6.25 / 7.5 / 12 |
| 向内伸出 | min(10, max(2, 0.20S), 0.35S) | 5 / 6 / 10 |
| 向外伸出 | min(12, max(3, 0.25S)) | 6.25 / 7.5 / 12 |

短边保护在极小时优先于名义下限；引线示意不代表真实300mm。第三页1:2，因此模型引线长度为纸面值乘2。同纸面尺寸不依代号或模型倍数；正方形始终顶部出线，长边引出在左。

导出后实际检查尺寸线段、箭头INSERT范围及锁定字体字形，与引线最小间隙≥0.25mm（0.18mm线宽并留余量）；另检查完整包围盒/绘图区/禁入区。三页最小间隙9.375/21.25/19mm。不能满足则拒绝，需用户调整比例，禁止自动换比例或默认放行。B04的完整比例推荐流程尚未实施，本轮没有提前实现B04。

尺寸显示新增六位小数精度与显式1e-6mm舍入，避免ezdxf把DIMRND=0的小数舍入成整数；整数样件外观保持。小尺寸自动移字/反向箭头按独立重建的受控缓存验证，完整缓存、字体、方向、位置及箭头防篡改检查仍保留。

证据：`lead-matrix.json`、`lead-matrix/*.dxf`、`scripts/check_lead_matrix.py`；测试 `tests/formats/test_lead_rule.py`。

## FreeCAD工具限制（DXF往返未通过）

实际软件为5090宿主Ubuntu包 `0.19.2+dfsg1-3ubuntu1`，`/usr/bin/freecad`与`/usr/bin/freecadcmd`，无Docker、无新安装、不下载旧导入插件。原生导入/导出、scaling=1、文字/布局开启。GUI在Xvfb显示环境启动原生FreeCAD后导入最终候选CX-26页时触发SIGSEGV，栈在libCoin `cc_rbptree_insert` / `SoChildList::append`；外层exit=1，见`freecad/gui-attempt.json`及`gui-final.log`。早期PySide/控制台上下文探查错误另留日志，不把脚本初始化错误说成图纸损坏。GUI崩溃后使用原生FreeCADCmd继续实际模型操作；没有成功的GUI字体/黑黄图框显示验收。

| 实际链路 | 结果与限制 |
|---|---|
| 输入DXF | 每页AC1032，毫米声明，45图框LINE、33文字、1闭合轮廓、2引线、2顶层原生尺寸，A4 viewport/layout存在 |
| FreeCAD原生导入 | 49个Part::Feature、33个App::Annotation、6个Draft尺寸；轮廓被拆成4条独立边，额外4个尺寸来自源文件未用块，不能称原生尺寸全被拆散 |
| 更新行为 | LinkedGeometry=[]、Support=None；改轮廓后尺寸不自动变化。显式改宽度尺寸End并recompute后25→30、30→35、100→105mm，FCStd重开保持 |
| FCStd | 实际保存`edited.FCStd`（FreeCAD项目）；轮廓、名称和尺寸编辑保持。无界面保存没有GUI字体属性，未验证显示字体保真；不能当DXF成功 |
| DXF导出/重开 | 实际`edited-export.dxf`文件头**AC1015（DXF 2000）**，三份均仅49条LINE；重开仍49个Part对象，无文字、无原生尺寸、无A4受控layout/viewport，只余STANDARD/ANNOTATIVE arial.ttf样式 |
| 单位/图框 | 导出无INSUNITS/MEASUREMENT声明；数值坐标量级仍匹配输入毫米模型，未观测25.4倍缩放，但不能称毫米声明保真。45条源图框线仅匹配43条，2条丢失（匹配容差0.01模型mm，实际匹配漂移另记） |
| 文字格式 | 导入Annotation中部分原MTEXT段落控制前缀未正确解释；FCStd文字值能编辑保存，不证明原排版/字体显示保真；无界面DXF导出则文字全部丢失 |

这些是当前FreeCAD 0.19.2构建、原生导入与**无界面原生导出链路**的实测限制，不能扩大为所有FreeCAD版本/导出方式的结论，也不能归咎于原DXF不含文字/尺寸。原候选经独立ezdxf严格读回通过，源文件单位/可编辑文字/尺寸/布局齐全。截图未作为可编辑性证明。

每页保留`freecad/<代号>/input-copy.dxf`、`edited.FCStd`、`edited-export.dxf`、`result.json`，均有hash；脚本`freecad_roundtrip.py`、独立输出检查`inspect_freecad_outputs.py`、宿主软件/命令`freecad/host-runtime.json`及汇总`freecad/summary.json`。原命令行循环stdout复用了一个文件名，只保留第三页控制台捕获；前两页原生执行的独立JSON操作记录和实际文件完整，未伪造控制台日志。

## 图纸自身问题与仍需处理项

1. 原候选本轮三页未发现越界、引线/标注冲突或技术文字贴标题栏；极小/超框边界已由实际读回拒绝。当前规则有明确可用范围，不承诺任意纸面尺寸都可排。
2. 源DXF保留原模板的未用历史块（含4个尺寸）；这是合法块内容，但本FreeCAD导入器将其额外实例化，造成污染。原始模板不为绕过工具限制而删改，后续如做未用块清理需单独验证；本轮不把6个导入尺寸称作正确布局。
3. 当前宿主FreeCAD的GUI字体/图框显示和可编辑DXF往返验收均未通过。FreeCAD测试副本不能用于交付；需在交付前可用CAD环境解决或验证，AutoCAD兼容性明确未验证。
4. 正式具名工程审批、CAD字体解析及接收方编辑/保存链路仍待交付前完成。`human-approval.json`继续pending，未虚构姓名、签字或批准时间；不阻塞本轮开发技术工作。
5. 本轮实现不能自行作为独立复审。调度将另行安排独立审查；B02独立技术验收通过且满足后批依赖后可按最新用户授权继续推进。FreeCAD不适配如实登记；只有确实阻断必要依赖且无法解决时才停相应批。

## 三页预览与最终文件

- 合并PDF：`docs/evidence/B02-development-baseline/candidate/heater-sample.pdf`
- 单页：`docs/evidence/B02-development-baseline/previews/page-1.png`、`page-2.png`、`page-3.png`
- 三页合览：`docs/evidence/B02-development-baseline/previews/three-pages.png`
- 视觉测量：`docs/evidence/B02-development-baseline/visual-review.json`
- 原始身份：`original-identities.json`；原fix-12报告：`docs/reports/archive/B02-fix-12.md`；旧独立审查：`docs/reviews/B02-final-fix12.md`。第一次生成尝试另留`attempts/initial-candidate/`，不作为最终候选。

## 自动验收与提交交接

`check_format_gate.py --stage development`核验真实矩阵、精确候选、FreeCAD输入/FCStd/DXF/操作记录及限制；默认`--stage delivery`保持原具名工程/AutoCAD门槛。本轮开发passed不表示加工批准。DWG探针未调用转换器，blocked符合延期范围，不能称DWG成功。

必要回归、B01当前源码依赖重验、统一B02 runner及最终两端HEAD/status/diff检查见本节后续结果。未改写`docs/orchestration/`，不覆盖本地调度原件到远端。

### 实际验收结果与最新授权收口

- 5090完整回归：**247 passed**（332.45s）；格式失败检测：**127 passed**（282.16s）。Windows引线矩阵12项、补充实际线段/字形冲突检查1项、开发/交付门槛7项均通过。
- 首次统一B02 runner所有代码/图纸测试通过，但注册表最后一个`--evidence`仍指向fix-12，导致开发gate读取旧证据并blocked。失败原记录保留于`attempts/pre-continuation/b02-runner/`。路径已纠正；错误调用写过的fix-12旧gate记录已还原其原字节（SHA-256 68ad6db22715f1e880917045b16f0422124a2b9783302bbf235c6b407f39f96f），历史候选和报告不变。
- 随后收到最新用户授权：不再要求整个项目停B02；独立技术验收通过且满足后批依赖后，调度可继续；只有确实阻断必要依赖且无法解决时停相应批。已更新计划/进度/决定/交接文字。当前执行者仍只完成B02，不自行开后批。
- 没有为文档变化重复247项完整格式回归。实际刷新了B01合同/规划运行器/ESM/安装前置检查，重新执行正确目录下的开发gate，并通过`revalidate_authorization.py`重建源码指纹，严格证明相对完成回归时仅改了`docs/contracts.md`、`docs/reference/requirements.md`及注册表中的gate证据参数；其余代码逐字节不变。旧127/247项真实测试记录、原源码版本和hash明确绑定，未声称第二次完整执行。
- 当前`b02-runner/summary.json`为 **passed**，`execution_mode=targeted_revalidation_with_explicit_reuse_of_unchanged_code_tests`，blockers为空。该结果是开发技术自验，独立审查仍待调度安排。`gate-result.json`为`passed_development_only`；正式交付`pending`，AutoCAD`unverified`，FreeCAD`limited`且DXF往返`failed`。
- 顶层原始运行日志受既有gitignore影响，已另存逐字节`raw-run-logs.zip`与`raw-run-logs.json`索引；实际原日志仍在工作区，未修剪失败日志或伪造输出。修改前的B01/B02证据及旧wheel另存`attempts/pre-continuation/`。
- 本轮没有遗留属于本项目的FreeCAD/FreeCADCmd/Xvfb测试进程；既有宿主其它CAD/RPC进程没有纳入清理。详见`process-cleanup.json`。交接payload的两端HEAD、status、diff --check和源码/候选有效性见`handoff.json`；包含交接记录本身的最后提交HEAD在本聊天最终回复列出，避免递归自引用。最后核对不重复代码回归。
