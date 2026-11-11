# B02 第五轮修复独立复审

结论：**FAIL。F04/F05 的指定旧反例已关闭，但同类尺寸缓存有效显示属性仍有完整 probe 漏检；F09 的真实运行字典仍可保留 token 后重绑到未执行过的输入输出。不能宣布技术闭环，也不能称为仅待人工批准。**

本轮仅写本报告、第四轮复审原字节归档 `docs/reviews/B02-rereview-4.md` 和新证据 `docs/evidence/B02-rereview-5/`。归档 SHA-256：`45e5371ce720ef696ddf6e1ccdd5e02cc838dafed489c06956cfd79d3ce8b145`。业务、测试、执行报告、冻结候选及模板、决定、编排文件均未修改；所有变异和政策夹具只在隔离副本或本轮证据内生成。未运行 ODA、真实 DWG 转换器或目标 CAD，未借用许可或代签批准，未进入 B03。

## 审查对象与身份

本地交接 HEAD `8fb59147c09abe968b0f9f0e17bb682b84fa8452`；实际开始 HEAD `284059b192490645f8c0a9987e8cb067a0e7f8f4`，其间为调度文档。远端开始 HEAD `677c38da9a2d1fe512f311e2fd390335bfa47686`。两端分支 `codex/b01-foundation`，实际源码契约指纹均为 `d3fa48868141a1bf146b275d231c794637f6deaf884cff56f4f63ba9853c97e9`，未机械地以纯文档 HEAD 差异判失败。

冻结目录 `docs/evidence/B02-fix-5/candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| candidate-manifest.json | fbc20a4ed55dda125af2d15ce9753d933ea80fe2d77ee190ba6293ac2f1f9064 |
| heater-sample.dxf | 7bc66cb55fb8ec845c01d5c0c2861f0ac4c903eff59100cc7b34fae5f246d5c4 |
| heater-sample.pdf | 2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f |
| drawing-pages.json | 003807dba99a90f40fbe7b44905da476a5df58a38841f4ae4495d1ceb46a8243 |
| reference-difference.pdf | 4d9c2c4037397a1b1bf6ded15d8c8506906f1b16412f5733ca850262777a7a87 |

当前模板 DXF：`b7a3e7221c002f08c9ebcf9bbc42917cf6c245840ff288c7a02d74c1368aec5d`。`sealed-facts.json` 独立核对整个冻结 candidate/template 与快照完全相同。两端最终分别核对原有 1,751 / 1,752 个保护文件，全部原字节不变；原有 state/events 历史差异分别保留，远端根 `.gitattributes` 未移植或修改。

已阅读 plan、B02、C02/C05/C06/C07、需求与基线、进度、当前及历史认可 B01、第五轮执行报告、旧复审，核查实际修复 diff、实现及测试；未发现适用 AGENTS。新证据保存实际 argv、cwd、日志和 hash；实际主快照路径为 `/tmp/heater-b02-rereview4-avl0cbn0/snapshot`，其中 rereview4 仅为继承的临时目录名称。归档映射及逐文件封存见 `evidence-index.json`，两端独立提交与干净状态见另行提交的 `git-handoff.json`。

## 独立执行结果

| 验证 | 结果 |
| --- | --- |
| 原注册默认 B01 CLI | **退出 0 / passed**；53 contract、47 planning；十项检查、ECMAScript、独立 wheel 安装通过 |
| 原注册默认 B02 CLI | **退出 2 / blocked**；62 格式测试、162 全回归通过，0 skipped；DXF/PDF probe 0；阻塞项为 human-gate-0、check-format-gate |
| 真实外部边界 before/after | 两条 CLI 0；严格验证器确认 passed / unchanged |
| Windows 完整回归 | **162 passed，0 skipped，退出 0，110.64 s**；原 log/xml/exit 保留 |
| Windows 时间戳五次定向重跑 | **5/5 退出 0**，旧偶发问题未复现 |
| 现有 24 个 DXF 负例 | **24/24 拒绝**，包含上一轮 20 项、三个完整缓存旧反例和 text_direction |
| 指定九项完整 probe | 退出码 **1,1,1,1,0,1,1,1,1**，顺序见下表 |
| 新增同类有效属性 | 四个有可视证据的错误缓存完整 probe 均 **错误退出 0**；另背景/厚度接受列作覆盖缺口，不夸大视图影响 |
| 当前原始 B01 绑定 | 新鲜原源码副本正例 passed，十二项变异均 blocked |
| 政策 CLI 子进程矩阵 | `test_b02_cli_matrix.py` **1 passed**，实际六次 CLI，退出 **0,2,1,1,1,0** |
| 完整注册 B02 政策夹具 | postpone 0、pending 2、required-blocked 1、required-claimed-verified 1；均在隔离副本 |
| 精确 CAD 证据 gate 夹具 | 直接 gate 合成正例 0；无关 DWG、缺人员、未来时间、错版本、缺动作各 2；并非转换/人工批准正例 |
| 三页 DrawingPage | C02 模型与共享语义校验全部通过 |

指定九项均使用真实 `scripts/probe_formats.py`，错误候选均刷新 manifest hashes，缓存五项同时修改单页和合并 DXF、重渲染所有 PDF/PNG，再生成合并 PDF：

| 序号 | 变异 | 退出 |
| --- | --- | --- |
| 1 | `_CLOSEDFILLED` SOLID 顶点变形 | 1 |
| 2 | 缓存 MTEXT 内联宽度 `\W0.2` | 1 |
| 3 | 缓存 LINE 明显改端点 | 1 |
| 4 | 缓存 LINE 改 0.001 mm | 1 |
| 5 | 缓存 LINE 仅 3e-14 mm 浮点噪声 | 0，合理 |
| 6 | 错误单页 PDF | 1 |
| 7 | 单页 PDF 横移 100 mm | 1 |
| 8 | 合并 PDF 第二页横移 100 mm | 1 |
| 9 | 黄色框线改黑，更新并重渲染 | 1 |

另将**仅合并 PDF 第二页**黄色描边改黑、更新其 hash，完整 probe 1，明确报 `FRAME_YELLOW expected (1,1,0), found (0,0,0)`。新增 ARC/CIRCLE/LWPOLYLINE 及 DIMENSION 本体 extrusion 负例亦拒绝。数值噪声并未被过度拒绝。16 个完整变异 probe 的整份候选输入已封存于 `full-probe-inputs/`，其全部 manifest artifact hashes 逐项匹配（`probe-candidate-archive.json`）。

服务真实根环境及版本记录于 `results.json`。锁文件 `service/uv.lock` 为 `7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60`。只读 `.tools/uv sync --project service --frozen --check` 明确指向真实根 `.venv`，退出 0，没有以临时审图环境替代服务依赖或更新锁。Windows 原始日志的路径编码乱码保留，未伪造修复日志。

## F01–F09 与新增要求

| 项目 | 处置 |
| --- | --- |
| F01 | **关闭保持**：24 页差异表、349 行、2,238 单元格、34,163 可见字形，0 越界；展示内容与数值映射逐项一致。 |
| F02 | **当前字形对齐关闭保持**；实际字体解析和独立轮廓测量合格。尺寸软件再生成漂移已修复，见下文；真实目标 CAD 尚未执行。 |
| F03 | **关闭保持**：引线、尺寸侧别及当前字形/图框/几何碰撞检查通过。 |
| F04/F05 | 指定旧反例全部关闭；**整类仍未关闭**，见 P1。 |
| F06 | 精确 artifact/人员/时间/版本/动作绑定与政策分支有效；真实 CAD 与项目授权 DWG 转换仍 pending。 |
| F07 | **关闭保持**：只读复审，原候选/模板及既有材料字节不变。 |
| F08 | **关闭保持**：当前三页 C02 通过。 |
| F09 | 导入 JSON、错内部输入、倒置时间、改名 Python、高熵垃圾等指定负例已拒绝；**运行记录不可变绑定尚有缺口**，见 P2。 |
| 黄色/黑色图框 | **本轮关闭**：三单页和合并三页各 21 段全部按实际端点/颜色匹配，含外框；两条完整颜色负例拒绝。 |
| B01 新模式 | 原始报告/源码指纹/Git HEAD blob 绑定有效，十二变异全阻断；历史唯一认可事实未改变。 |
| 当前 runner 证据根 | **本轮关闭**：执行器及独立 B02 summary 所有 evidence input/artifact 均来自 fix-5；污染旧 fix-3 不影响当前 built-in。 |

差异表源线段为 55/55/65；各匹配 4，未匹配 51/51/61；候选各 21，其中未匹配 17，均与实际展示集合相符。每页候选文字 41 项，源文字语义保持 unknown/approval，未从轮廓凭空认定准确文字。三张候选、源图联系表、24 页差异表联系表以及第 1/12/24 页完整图均已目视检查。

实际字体 OTF 为 `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`，PostScript `NotoSansCJKsc-Regular`；源 TTC `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a` 的 **face 2**。独立读取实际文件 name 表及系统包 copyright，许可 SIL OFL 1.1；未分发字体二进制，未选择许可不明 HZDX.SHX。原 TEXT/缓存 MTEXT、MTextExplode 完成后的实体、软件再生成三个阶段均锁定实际同一字体。独立比较 129 实体、876 字形、12 箭头，最大字形误差 **0.0000170093 mm**，箭头边界误差 **0.0000172347 mm**，碰撞 0；单页与合并对应页像素一致。

六个原生尺寸均经 ezdxf 再生成两次、保存重开、再生成，独立完整缓存语义相同；原报告中的软件再生成位移现为 **0 mm**。进一步在隔离副本修改尺寸**定义点**：宽向 +5、长向 +7，六个测量及缓存显示分别正确更新为 35/57、30/32、105/307，保存重开后稳定。这里未声称修改加热片轮廓后关联尺寸自动更新，亦未将 ezdxf 软件试验冒充 AutoCAD 验收。证据 `dimension-review.json`、`dimension-software/`。

## 必须修复的发现

### [P1] 缓存有效显示属性仍可绕过完整验收（F04/F05）

位置：`service/src/heater_drawing/drawing/readback.py:88` 的 `_cache_entity_signature` 及 `:188` 的独立期望缓存，比较于 `:613`；同时涉及 `pdf_renderer.py:35/148/191` 对有效显示属性的处理。新增签名虽覆盖几何、原始 MTEXT 格式和 INSERT 子图元，却遗漏 `invisible`、`true_color`、缓存 MTEXT `extrusion` 等属性；实际渲染/读回比对也未将这些错误缓存与正常原生尺寸的应有显示统一验证。

可复现：对第一张 `CX-29-KR05-XM01` 的首个 DIMENSION 缓存逐项应用下列变异，**单页及合并 DXF 同时修改**，用真实渲染器重建全部页和合并 PDF、刷新全部 hashes，再完整运行 probe：

| 变异 | 独立 ezdxf 显示解释（白底黑前景） | 完整 probe |
| --- | --- | --- |
| 缓存 MTEXT `invisible=1` | 水平“25”消失 | **0 / passed，错误** |
| 缓存首个 LINE `invisible=1` | 一条尺寸界线消失 | **0 / passed，错误** |
| `_CLOSEDFILLED` SOLID `true_color=0xffffff` | 白底箭头消失 | **0 / passed，错误** |
| 缓存 MTEXT `extrusion=(0,0,-1)` | 水平“25”镜像；产品 PDF 亦出现镜像 | **0 / passed，错误** |

前两项及真彩色还使产品 PDF 仍画出本应隐藏/白色的内容，暴露 DXF/PDF 不一致；extrusion 则产生与正确尺寸不符但相互一致的错误图面。不是 stale PDF 或未更新 hash 的假反例。`cache-review.json` 记录十一完整 probe；对应 `cache-full-*/validation/probe-result.json`、全部原始日志及 `full-probe-inputs/` 可复验。独立前端使用 `ezdxf.addons.drawing.Frontend/RenderContext/MatplotlibBackend`，图示 `visual/native-display-comparison.png`；这只是独立软件解释，不是实际 CAD 观测。

背景填充、LINE thickness 也被接受，列作同类属性覆盖不足；不将其在当前平面视图必然造成肉眼缺陷作结论。连续线的 ltscale=10 接受也不单列缺陷。建议对受控缓存的实际有效属性进行完整规范化比较，或严格拒绝未批准的显示属性；渲染器与 probe 必须一起覆盖继承颜色、可见性、OCS/挤出变换及相关显示控制，并维持正常噪声容差。不能只补四个固定值断言。

### [P2] 真实 runtime token 未绑定其原始执行内容（F09）

位置：`service/src/heater_drawing/drawing/dwg_adapter.py:20/116/165/648`。真实 helper 返回的字典携带模块单例 `_runtime_provenance`；验证器检查 token 身份及**当前可变字段**，未以不可变快照/受认证摘要绑定 helper 实际执行时的 argv、PID、起止时间和输入输出。

本轮真实执行一个普通 Python 复制 DXF 子进程，取得合法 token（不是自行导入模块 token 或伪造 JSON）。原字典验证返回 None；序列化后重新导入立即拒绝，说明第五轮导入防线有效。然后保留该真实 token：单独替换从未执行的 argv、PID=12345 或另一组顺序合法时间，验证仍返回 None；进一步将内部 input/output、argv 一起重绑到**两个从未被该命令处理过、字节不同的有效 DXF**，刷新其路径/hash/size/mtime，并以重绑后的文件作为 verifier 参数，仍返回 **None**。持久化执行记录及其 descriptor 未能约束当前运行对象。

精确证据：`receipt-review.json` 的 `runtime_mutations`、`runtime_rebind_unexecuted_error: null`，`helper/rebound-record.json` 与真实 helper logs。单独改错输入、可执行 hash、输出 hash、倒置时间、外层正确而内层错误均拒绝。真实普通 Python `--version` 夹具在同进程通过、导入后及倒置时间被拒绝；它输出的 ODA fixture 字样不代表执行 ODA。

这是**同进程回执组件绑定缺陷**，不宣称当前完整 Linux 或已签名 Windows capabilities 可被绕过：默认 not_configured；Linux 无可信 vendor 签名/digest 时拒绝改名 Python，Windows 实际复制 Python 改名也 unverified，且本轮高熵假 DWG 均 structure unverified。当前实现对所有实质 DWG 也 fail closed；没有实际转换正例。修复应令真实执行产生的完整规范记录不可变，或由 helper 保存可信摘要并对每次验收重新校验；仅在字典附单例 token 不足以证明内容就是实际运行内容。

## F09 正向行为及证据边界

普通 helper 的 6001 字节 stdout、6001 字节 stderr 均完整落盘并校 hash；退出 7 被拒绝，0.15 s 超时记录完整双流、子进程组清理后 sentinel 不存在。无输出、旧输出、普通垃圾、header-only、低熵填充和高熵垃圾均拒绝。原始根 UV 环境只读检查通过。所有程序均为普通 Python；复制/改名的 Python 仅作静态身份检查，未执行。Windows 的复制程序 hash 为 `7283f7d271f7de55cc7fd290efbcc274119655f99bfb676de7f1036e2fc59e08`，未入库。

完整政策夹具中 `postpone-contradictory` 为继承名称：改名程序现已不可信，实际 capability 是 unverified，所以该 full B02 的退出 0 不构成“已验证却延期”的矛盾分支；真实矛盾状态由独立六次 B99 CLI 夹具覆盖并拒绝。合成 license/approval/decision/CAD 内容仅用于分支试验，不是许可或工程批准。直接 gate 的受控正例人为注入合成 capability，仅隔离验证精确 CAD 绑定，不声称 capabilities 接受、实际 DWG 转换或操作员批准。

## B01、runner 与证据完整性

原始当前 B01 summary hash `3b60fe34dca5c4b068791d7307ec7c832431aebdc68e71430c88fcd5cb9f94f3`，binding hash `df0235638e7eb9471bf075d6158dbd67de355be4fb7b64ed6937febfbca58eba`；源码执行 HEAD `23e8aeb5ac5e054f97b71f5f7c000e66f05baa57`，绑定提交 `64c01fbec79f460caec2745ff0e54c07d937f13a`。fresh clone 用原源码、原报告、原绑定正例通过，十二变异全部 blocked；另真实完整 B02 对删减命令的当前 B01 报告退出 2。历史唯一认可 `B01-fix-2-r2/summary.json` hash `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0` 未改变。

两份 B02 summary 的 evidence inputs/artifacts 均归属于当前 fix-5；执行器 dirty_files=[]，独立 B02 如实记录先前独立 B01 输出 `?? docs/evidence/B02-rereview5-b01-current/`，未伪报 clean，该项不代表源码脏。注册缺命令、重复命令/flag、逃逸路径、仅 evidence 根、缺 flag 值均拒绝；解析到项目 evidence 内的绝对路径合法。独立新副本污染旧 fix-3 的 probe 后当前 built-in 全通过，说明不再混用旧根。

执行器第四轮归档 `docs/reports/archive/B02-fix-4.md` hash `50b3ac27aa192f60ebd3ccfdffd7191521b004baa9408ae55cabb58c8ceafafc` 保持不变。审查方法更正均保留原始文件：尺寸初版未规范化 DXF 缺省 rotation=0；颜色初版未展开 PDF qu/re 外框；runner 初版误将 evidence 内绝对路径及审查输出判错；CLI 首次 `-k subprocess` 未选测试，随后六个函数测试不冒充子进程矩阵。最终结果分别来自 final JSON 及正确 `test_b02_cli_matrix.py` 的 log/xml/json。Windows 回归元数据是事后索引，不冒充实时签发回执。

两端独立原有清单、source entries、旧报告归档、本报告和全部新证据均做字节/hash 核对，逐项见保护清单、`source-mirror.json`、`sealed-facts.json` 与 `evidence-index.json`。最终 content commit 分别独立产生，既有编排历史不合并；提交后再记录 handoff，最后核对两端 clean、staged/unstaged diff-check 与 Git blob hash。

## 后续边界

先关闭上述 P1/P2，再重新复审；当前仍有技术缺口，因此“只剩人工项时提交批准包”的条件尚不成立。模板/字体替代、引线参数、精确候选目标 CAD 编辑更新保存重开、工程批准及 DWG 首发范围决定均保持 pending；不在本轮请求或代替这些批准。到 B02 为止。
