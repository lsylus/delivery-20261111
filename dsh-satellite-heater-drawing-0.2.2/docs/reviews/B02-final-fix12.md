# B02 fix-12 最终独立验收

结论：**自动化技术复审 PASS，上一轮 3 项 P2 已关闭，新增技术必修项 0。B02 正式总体验收仍为 blocked，不能记为 PASS。按用户“这一轮验收不过就先停”的要求，完成报告和两端提交后停止 B02，不发起 fix-13、B03 或后续 Batch。**

这是 DSH 矩形加热器插件的前期模板与出图组件验收；CLI 为内部验证入口，完整 DSH 插件尚未交付。首发 DXF/PDF、产品 DWG 延期的决定已完成，一次性原模板 DWG→DXF 与产品 DWG 支持分开。具名审批保留在交付前，未因人员缺失中止技术审查。

仅修改本报告、新建上一轮报告的原字节归档 [B02-rereview-11.md](B02-rereview-11.md) 和 [本轮证据目录](../evidence/B02-rereview-12/)。归档 SHA-256 为 `0a810fec04a6d377169789a9aa1e1f527448bc930ab9c4d53505a327090d33fa`。业务、既有测试、冻结候选、模板、registry、决定、执行报告、旧证据与 orchestration 按两端各自原件保护；未运行真实转换器或目标 CAD，未创建真实批准，未启动新聊天或子代理。

## 身份与范围

本地起点 `0f1d990a8531a9e8d1001240584199a9deb39e89`，远端起点 `a18a2719759b2e2b6ae8659f3847b16be61b65a3`，分支均为 `codex/b01-foundation`。创建复审目录前两端 clean，无适用 AGENTS。源码契约一致：

`1fbf98d6404ab333da526b0a59f53133ba6d427027ed30c278294297269b27f5`

| 冻结对象 | 实际 SHA-256 |
| --- | --- |
| candidate manifest | 3e85427c53d592554cdb1b6782ca3c1e6ec36c0feff19d16318685d455ecdd43 |
| template manifest | 4dffba2276771ca1bf3f02308c9ce0fc6b83b9898b5da1528b9783837cd3ea3c |
| layout | 67d25abea563049c85ef1098f49af21077141230f17e785707d12b0c888f5b73 |
| font profile | f7c755b57d89aaf89b4e4c8505b9737c440cb1e8f0345b590ea5e869ea329cb5 |
| 原始一次转换 DXF | 9bcca3259ef7881af10e640538ec9cd8947bce7d86ee30f18e0c20f7cc8b4c15 |
| 受控 template.dxf | 3bcf858e7417f304bcaf7100abc1b8fa111dad76a070337f790b687edf5415c7 |
| Noto OTF | e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322 |
| 汇总 DXF | a7b203d5b686953eac4af410c7de94af8e0668e1f33c30742cd897e246912f82 |
| 汇总 PDF | d85e36df5a775f0a8adb611d2af3e24a989467009508b5c02e94cabde627ff0b |
| 28 页差异 PDF | fdd67872560a2b0a01e4360a148710c51c3fe5e62e98e6aca62b595a3c68f4f7 |
| 当前 pending | bec30296d00223c90e5d027fefe6f5cf10b16ac169fc024832a3682200150dbf |

两端独立校验 candidate、probe、template 与 human 绑定的实际文件哈希。读取 plan、B02、C02/C05/C06/C07、R02–R04/R07、原始用户审阅、上一轮复审与本轮执行报告；检查 writer、readback、renderer、字体度量、模板刷新/加载、probe 和测试变化。实现 diff 保存在两端对应的 implementation-diff 日志。

## 三项 P2 的关闭依据

**1. 原生 MTEXT 格式保留：关闭。** Writer 按明确 content policy 安全替换占位值，保留原 `\pxqc;` 居中段落和 `\H1.042x;` 局部字高；技术要求使用独立 Unicode 分段规则。三页 33 个字段的源 raw、实际替换 raw，以及两侧使用同一个锁定 Noto 字体实际展开的字形边界全部匹配，位置差小于 1e-8 mm。反斜线、花括号及类似格式指令的字面输入经转义仍原样读回。型号已恢复段落居中，不再有上一轮约 16.958 mm 左移。见 [native-text-review.json](../evidence/B02-rereview-12/native-text-review.json)。

**2. 有效格式与实际字形范围：关闭。** Readback 比较解析后的内联/段落格式、flow 和行距，恢复非零 glyph box 的 cell/paper/frame/overlap 检查，complete_content_box 纳入文字与尺寸文字。独立完整候选同步修改全部三份单页与汇总内所有对应行，刷新并核对 artifact hashes 后运行正式 probe：

| 变异 | 单页及汇总 readback | 完整 probe | 视觉件处理 |
| --- | --- | --- | --- |
| H3、W3 | 均拒绝 | 各 1 | 三页 PDF/PNG 与汇总 PDF 真实重建 |
| C1 红色 | 均拒绝 | 1 | renderer 拒绝 ACI 1，恢复原冻结视觉件并重新绑定，未声称重渲染成功 |
| flow_direction=3 | 均拒绝 | 1 | 全部真实重建 |
| H1、W1 | 均接受 | 各 0 | 全部真实重建 |
| 显式来源默认值、3e-14 浮点噪声 | 均接受 | 各 0 | 全部真实重建 |

边界隔离实验仅在独立进程注入诊断 expected records，以绕过更早的位置锁，未改产品源码，也不充当完整候选接受证据。真实字形越 cell、越纸、新框线穿越、文字重叠分别在对应检查处拒绝。固定文字 allowed_frame_crossings 与实际原字形重算一致，没有全局免除框线检查；字段 cell 来自原图框分格。技术区 0.25 mm 是 cell 四边容差，当前左侧外伸约 0.191067 mm、底部最大约 0.170167 mm；仍在纸内且不穿框。诊断 0.20 mm 通过、0.30 mm 拒绝，paper/frame/overlap 检查继续生效。见 [boundary-text-review.json](../evidence/B02-rereview-12/boundary-text-review.json)。

**3. 原生尺寸 PDF 额外 0.8 缩放：关闭。** 配置把 HZ→Noto 替代补偿 0.8 与原生 HEATER_CJK 尺寸 1.0 分开。独立用实际 DIMENSION cache 的 MTEXT→TEXT→glyph paths 测原生边界，再直接读取冻结单页和合并 PDF 的可见 fill；没有把产品新度量函数或 renderer canonical 当独立期望。六处实际宽高比范围 0.999997313–1.000001927，最大边误差约 0.000009961 mm；Windows/Linux 原生展开边界差为 0，产品单行度量与独立展开最大差约 2.85e-14 mm。原完整尺寸 cache 签名仍继续比较，没有被新 bbox 替代。见 [cross-platform-text-metrics.json](../evidence/B02-rereview-12/cross-platform-text-metrics.json)、windows-native-metrics.json 和 native-text-review.json。

## 其他核验

原始转换 DXF 与受控模板的 78 个模型实体逐个比较，仅平移 `[-2826.401843915681, 4438.726129851452, 0]`，无缩放；45 LINE、19 MTEXT、14 TEXT 及原图层、文字样式、dimstyle 保留。模板 DXF 与上一轮同字节；原 DWG、HZDX、一次转换证据保持原哈希，本轮没有再次执行 ODA。原一次转换 argv/exit 与来源限制保留在归档第十一轮证据。

Excel 三行 A:Q 共 51 字段与 fixture、冻结 DXF 一致；第二页标审按 O3“郑玲”。数量原文、电阻/偏差、人员职责、空工艺栏和固定文字已核对。真实几何保持 25×25、30×50、100×300 mm 与 1:1、1:1、1:2，没有复制原 PDF 约 1.042 的放大。样例引线间距约 5.3018/9.9942/15.0015 mm，非样例 fallback 10/10/10 mm、中心 (88,187)，仍待工艺接受。见两端 provenance 和 [excel-field-check.json](../evidence/B02-rereview-12/excel-field-check.json)。

六个原生尺寸重复 render、保存、重开、再次 render，并改实际定义点 +5/+7 mm，测量与可见数值正确更新且保存重开稳定。这是 ezdxf 软件实验，**不是 AutoCAD 证据**。直接 Continuous cache LINE 非法颜色、源 dimstyle 虚线而 cache Continuous 的完整反例，readback、renderer、probe 均拒绝。原 runtime receipt、display、runner、C07 实现与上一轮交付字节相同，结合本轮回归继续覆盖，见 unchanged-previous-defenses.json。

已渲染并目视最终三页全图、原标题栏/会签栏、技术区与标题局部；另用 Poppler 渲染三页复核。未见缺字方框、字段覆盖或新框线冲突。Noto 与原 SHX 风格仍有明显差异，不能据此认定外观已获工程接受。差异 PDF 全 28 页接触表已查看；独立核对 415 行实际内容、2658 个 cell、44231 个可见字形、源线段覆盖及距离计算，无表内溢出或内容错配。表内 pending 不等于已批准或逐线相同。见 [difference-audit.json](../evidence/B02-rereview-12/difference-audit.json) 与 visual/。

## 命令与门槛

| 独立执行 | 结果 |
| --- | --- |
| 新鲜快照默认 B01 CLI | exit 0 / passed |
| 新鲜快照默认 B02 CLI | exit 2 / blocked |
| Linux 正式 DXF/PDF probe | exit 0 |
| Linux 格式测试 | 127 passed，288.71 s |
| Linux contracts/planning/formats | 227 passed，321.97 s |
| Windows 独立格式测试 | 127 passed，270.56 s |
| Windows 精确冻结候选只读 probe | exit 0，候选未变 |
| DWG capability probe | exit 2，按延期决定非必需；未执行真实转换器 |
| format gate | exit 2，真实审批 pending |

完整 argv/cwd/exit/log hash、环境与默认 runner 见 [results.json](../evidence/B02-rereview-12/results.json)、b01-current/、b02-current/、windows-checks.json。Windows 未新建 Linux wheel/路径的替代绑定，执行方既有 Windows 完整 CLI 失败原样保留，不能宣称统一 CLI 两端成功。

原当前 B01 接受绑定在新鲜 clone 中通过；12 个缺项、改源、改日志、过期/未来时间、仅重绑摘要等反例拒绝。历史获认可 B01 摘要仍为 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。当前 evidence root、错误路径和旧 probe poisoning 均核对，runner 消费 fix-12；新鲜 B02 的 dirty 仅为先前生成的 reviewer B01 报告目录，source 未变。

当前 C07 登记窗口和本轮新采集窗口重算均 unchanged；历史 changes_observed/unknown_external 按原基线重算保留，没有归咎、回滚外部项目或冒充当前状态。见 [pending-boundary-review.json](../evidence/B02-rereview-12/pending-boundary-review.json) 与 boundary-validation.json。

当前 pending 绑定精确候选、模板、字体与全部实际 artifact hash；actor/role/time/conclusion 为空，目标 CAD 十项动作 false。审批契约 9 个变异拒绝；新鲜 clone 生成器 payload 相同，原件 CRLF/生成 LF 的实际字节差异如实记录，未改写 active pending。B02 blockers 为 human-gate-0 和同一 pending 导致的 check-format-gate。

未成功的复审尝试均保留：只读 fixture 直接赋值、诊断 overlap 身份设置、误把源 flow=5 写成 flow=1 的“默认值”实验、初版脚本误复制 fix-11 runner 视觉证据。只修正复审脚本；最终正例使用来源实际值，错误拷贝另存 attempt，正式 runner-* 来自同一新鲜快照当前 fix-12 输出。旧尝试不作为最终通过证据，见对应 attempt 文件和 runner-copy-correction.json。

## 最终状态与停止边界

| 事项 | 结论 |
| --- | --- |
| fix-12 技术复审 | **PASS，必修项 0** |
| 原生模板映射、HZ/Noto 外观、引线与 fallback 工艺接受 | **待工程确认** |
| 精确候选真实目标 CAD 的打开/编辑/尺寸更新/REGEN/保存/关闭/重开 | **未验证** |
| 具名正式批准与 B02 总体门槛 | **pending / blocked，未通过** |
| 首发产品 DWG 范围 | **延期决定已完成** |
| 项目动作 | **停在 B02，不开下一轮修复或后续 Batch** |

两端各自 9764 个原 tracked 文件受独立 hash 保护，不同步 orchestration 或历史。报告、归档、新证据以 index 核对工作树、精确暂存 blob 和内容提交，再分别提交同一交接记录。保护结果、源差异、提交身份与最终 clean 状态见 source-mirror.json、evidence-index.json 和 [git-handoff.json](../evidence/B02-rereview-12/git-handoff.json)。
