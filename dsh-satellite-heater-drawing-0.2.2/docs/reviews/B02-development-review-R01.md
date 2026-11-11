# B02 开发基线独立审查

**开发技术验收 FAIL：1项P2必须修复。** 冻结三页、技术文字移动、统一引线矩阵检查通过，但本轮六位小数尺寸被读回器误拒绝。247/127项自动测试未覆盖这个真实反例，不能据此PASS。未授予加工批准、未启动B03或其他聊天。

日期：2026-11-09（Asia/Shanghai）。最新用户决定优先：接受fix-12外观及当前PDF字体，技术要求右3/上8mm，统一短边纸面引线；FreeCAD限制如实记录，具名审批留交付前，AutoCAD未验证，产品DWG延期。旧“整个项目停B02”条件不再适用。

## 身份、范围与读取依据

本地根 `C:/Users/HUAWEI/Documents/ChatGPT/矩形加热器插件/heater-drawing`；Linux权威根 `5090-qmh:/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing`。两端分支均 `codex/b01-foundation`。最初只读检查本地0dee3f1、远端e0c102fb7914，均clean；证据捕获前调度另提交本地2e3b98e（审查登记），实际起点见 `start-win32.json` / `start-linux.json`。实现本地2680390e731b与远端e0c102fb7914的源码内容一致。未发现适用祖先或项目内AGENTS.md。

实际阅读plan、B02、contracts C02/C05–C07、requirements、project-baseline、progress、开发决定、实现报告、B01交付及独立PASS、fix-12独立审查归档，并核对B03/B04依赖。直接检查本轮diff、leads/sample/profile/writer/readback、字体度量/renderer、gate/registry/runner及相关测试，读取真实DXF/PDF/PNG/FCStd、操作JSON和日志；未用原实现者自审。

独立证据均在 `docs/evidence/B02-development-review/`，下文路径相对此目录。只修改本报告/该新目录；业务、既有测试、计划/决定、执行报告、冻结样件、历史和两端orchestration不变。统一CLI在该目录内独立Git快照运行，避免写回既有证据；snapshot/和pytest-temp/保留为忽略的复现临时目录，正式反例/命令/日志/产物另行入库。

两端源码指纹均为 `aae8cce63228d45dbaed9a27c1562c109ea5f286c0e54e24691275c55b36a2b9`。候选manifest为 `0fc298cd05e459fe7dc33a42046f0b05db3ffd90b295305e4747bc233cfcfbd7`，汇总DXF `17063429cc26ab0773724d4ddb8e0131f049ed8ea4595a8538a73c1a07fac3e0`，PDF `166f6ac84ab2d81111f22690f78ab26f16b49740a1152c035225454b5161a06e`。

## 必修 R01 / P2：六位小数与六位有效数字不一致

位置：`service/src/heater_drawing/drawing/readback.py:990`，与本轮profile.py的DIMDEC=6、DIMRND=0.000001不配套。

触发：合法 **12.123456×37.987654mm、1:2、长边出线**。独立调用当前 `_plan_page`、`write_page_dxf` 生成真实DXF，再调用 `inspect_dxf`，Windows/Linux均复现：

| 项目 | 宽度 | 长度 |
| --- | --- | --- |
| 原生测量 | 12.123456000000004 | 37.98765400000002 |
| 正确可见缓存 | 12.123456 | 37.987654 |
| `f"{value:g}"` 错误期望 | 12.1235 | 37.9877 |

默认g是六位**有效数字**，不是六位**小数**。宽度处报 `ReadbackError: dimension cached display text drift for Sheet1:2/width`。并非无效输入、单位漂移或人为篡改，而是受控writer自己生成的正确缓存被拒绝。模型/原生测量正确，诊断PDF/PNG真实渲染成功；诊断件不作为已通过候选。

影响：超过六位有效数字的正常小数尺寸不能完成导出后验证，B04复用将把合法行判失败。既有矩阵仅覆盖12.5等简单小数，不能证明本轮六位精度能力完整。

复现：两端分别用项目 `.venv` Python运行 `docs/evidence/B02-development-review/precision_repro.py`。证据为 `precision-linux/result.json`、`precision-win32/result.json` 及各自真实DXF/PDF/PNG；最初失败件还保留在 `small-controls/original.dxf`、`precision-inspect.json`。

另以 `--wide` 生成40.123456×80.987654mm、1:1的宽裕图面，仍得到40.1235/80.9877错误期望并拒绝，真实渲染未见引线/尺寸冲突；见 `precision-wide-linux/`。因此R01并非极小图面空间不足造成。

修复要求：独立按受控DIMDEC/DIMRND及尾零规则计算可见期望，不得取候选缓存作自身期望、删除完整缓存/文字/字体/位置/显示检查或宽泛放行近似数字。增加超过六位有效数字、六位小数、舍入边界正例，两端通过；缓存数字/位置/箭头/字体/显示篡改仍须拒绝。修后执行受影响格式测试、精确三页probe和本反例；无新影响不机械补跑无关全回归。

## 实物核验结果

**三页及文字。** 两端逐项核对8组hash map、15项validated candidate文件和命令日志。三页均AC1032、INSUNITS=4、33个可编辑文字及2个顶层原生DIMENSION，轮廓/测量25×25、30×50、100×300mm，300mm技术要求不变。独立 `pdftoppm -r 120 -png` 重渲染并逐页查看，未见新缺字/越界/覆盖。直接读取PDF fill路径，相对fix-12技术区四边右3/上8mm，最大位移误差约0.000015mm。

PDF实际技术字形横向约134.797–184.139mm，右纸边余量 **25.861mm**、右内框余量 **16.099mm**；底部57.908–57.951mm，距实际标题栏顶线49.761904mm为 **8.147–8.189mm**。实现报告15.148/5.386/8.068–8.121mm来自readback锁定替代字体的较大字形盒，不是PDF实际fill盒；两者均留足空隙。未把用户已接受的Noto/SHX差异作为阻塞。见 `artifact-audit-linux.json`、`artifact-audit-win32.json`、`previews/`。

**引线与碰撞。** 逐份读取11份矩阵DXF真实端点，独立重算S及三条公式，全部吻合；同纸面尺寸跨代号/比例一致，正方形上出线。实际重跑 `check_lead_matrix.py --output docs/evidence/B02-development-review/independent-matrix`：9接受、2预期拒绝。另独立展开真实尺寸线/箭头及锁定字体字形，计算与引线距离：9个接受件均≥0.25mm，极小0.5×1mm纸面确有0.1mm间隙并拒绝，150×300纸面超框拒绝。见 `clearance-audit.json`，没有只信planned checks。

**旧防线。** 另建12.5×37.5mm、1:2真实正例，以独立文件修改缓存数字、文字位置、线颜色、HEATER_CJK字体宽、DIMDEC、箭头缩放，6例全部拒绝。完整缓存仍从受控样式独立重建，小尺寸移字/反箭头未取消字形/方向/箭头/显示约束。见 `targeted-review.json`、`small-controls/`。该结果不掩盖R01。

**B01与复用。** 历史接受仍唯一为B01-fix-2-r2/summary.json，实际hash `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。当前绑定、日志/输入/产物/hash、源码指纹、时效及登记boundary均通过。逐文件从被测试提交重建旧指纹，确认源范围仅contracts/requirements继续授权文字和registry的gate证据参数变化；代码/测试不变，旧247/127日志和原版本来源真实。plan等交接变化未改变schema/API。见 `targeted-review.json`，没有运行实现方revalidation脚本代替独立核查，也未追逐外部仓库永远不变。

## 命令与保留的失败尝试

完整argv/cwd/exit见 `linux-commands.json`、`windows-commands.json`、`gate-commands.json`及各脚本/输出。

| 独立执行 | 结果 |
| --- | --- |
| Linux统一B02 CLI格式失败检测 | 127 passed，288.88s |
| 同次CLI contracts/planning/formats | 247 passed，332.88s |
| 同次CLI冻结DXF/PDF probe | exit0 |
| Windows引线/开发门槛定向回归 | 20 passed，31.15s |
| Windows精确冻结候选probe | exit0，候选未改 |
| 实际引线矩阵重跑 | 9接受、2预期拒绝 |
| 开发gate命令 | exit0 / passed_development_only |
| delivery gate命令 | exit2 / 正式审批pending |
| 两端高精度反例 | 正确生成/渲染，读回误拒绝，确认R01 |

审查准备遗漏原样保留：独立clone没有Git忽略的wheel和`.tools/uv`，首次B01 exit1，补wheel后仍缺uv而exit2；补齐权威根同一wheel/工具后 `cli-B01-ready/` passed（53 contracts、47 planning、Node、真实wheel隔离安装、foundation和登记boundary）。初次B02启动时缺wheel已记依赖blocked，其后4项必需命令实际全部passed，最终exit2，未伪称该次CLI exit0。`recheck_cli.py`验证本次CLI全部日志hash和源码指纹不变，仅重查依赖/builtin，写 `cli-B02-final/` passed；没有第二次执行247/127项。这个机器passed不改变独立R01 FAIL。

独立脚本曾误将frame-line图层名当颜色、直接比较未容差float、诊断ezdxf参数错误，相关attempt日志保留；仅修审查脚本。初次高精度失败继续保留作为R01，另建简单小数正例检查旧防线，没有改测试以消除失败。

首次暂存diff检查将FreeCAD原始stdout的横幅空格/回车进度视作尾随空白；保留日志字节，仅在新证据目录将*.log登记为binary，未修剪日志。初次index及原因保留于staging-attempt.json和attempt-evidence-index-before-log-attributes.json。

## FreeCAD工具限制、AutoCAD及正式交付

核对宿主dpkg版本0.19.2+dfsg1-3ubuntu1、可执行路径、原GUI argv/日志/hash。原GUI导入最终CX-26页日志确有SIGSEGV，栈含libCoin cc_rbptree_insert / SoChildList::append，区别于早期PySide上下文错误。未为凑截图重复崩溃，GUI字体/黑黄图框显示仍未验证。

独立使用宿主FreeCADCmd打开实现者三份真实edited.FCStd，确认+5mm轮廓、名称-B02EDIT和显式尺寸保持。再从三页精确候选副本重新导入，四边独立加宽 **7mm**、名称追加-INDEPENDENT，重算、显式更新、存FCStd、关闭重开、导出DXF、关闭重开。保留 `freecad/` 实物及 `freecad-independent.json/.log`。

| 链路 | 实测结论 |
| --- | --- |
| 原DXF | 2顶层原生尺寸、33文字、45框线、mm及A4齐全 |
| 原生导入 | 49 Part、33 Annotation、6 Draft尺寸；其中4个尺寸来自未用历史块，不是正确两尺寸布局 |
| 更新行为 | LinkedGeometry空、Support=None；轮廓+7后仍25/30/100；显式改End后32/37/107mm，FCStd重开保持，误差<1e-6mm |
| FCStd | 三页轮廓/文字/显式尺寸编辑保存通过；文字残留段落前缀，未验证GUI字体/排版保真 |
| 实现及独立DXF导出 | 每份AC1015、仅49 LINE，无文字/原生尺寸/mm声明/受控A4 viewport和layout；重开相同 |
| 框线/单位 | 原45线仅43匹配、2缺失（0.01模型mm容差）；未观察25.4倍整体放大，仍不能称单位声明保真 |

这些仅限**当前宿主FreeCAD0.19.2构建、原生导入和无界面原生导出链路**，不扩大为所有版本。FCStd通过不等于DXF往返通过；不归咎于源文件缺文字/尺寸，不声称AutoCAD通过。历史未用块导致该导入器污染仍为交付风险，后续清理须单独验证。本轮按用户决定不以这些已如实调查的工具限制额外阻塞开发。

正式加工交付 **pending**，AutoCAD2018 **未验证**。交付前仍须精确最终产物的具名工程批准，目标CAD字体/图框/文字编辑/尺寸更新/保存关闭重开/单位及布局实测；当前失败FreeCAD链不能代替。字体/模板/候选变化须重新绑定批准。产品DWG延期，未运行转换器、未新增许可或兼容批准。

## 后续依赖与提交边界

**B02技术FAIL，R01修复并独立复验前，B04的B02前置不满足。** B03文档技术依赖仅B01，本次已核验有效，且不消费此出图精度逻辑；调度按最新授权和真实依赖处理排程，不把工具限制或旧停B02条件扩大为整个项目永久阻塞。本审查不启动后批。

两端起点、完整保护、HEAD/branch/status --porcelain/diff --check和进程状况见 `start-*.json`、`final-protection-*.json`、`handoff.json`。仅暂存本报告/新证据，不重置/删除成果制造clean，不复制orchestration。最终自身提交hash以Git HEAD及最终聊天交接为准，避免自引用。完成提交后停手。
