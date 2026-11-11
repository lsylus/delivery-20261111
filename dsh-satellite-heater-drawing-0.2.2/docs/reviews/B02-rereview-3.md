# B02 第三轮修复独立复审（F01–F09 与 B01 依赖模式）

结论：**FAIL。仍有可独立复现的技术缺陷，不能宣布技术闭环或仅待人工批准。** 真实目标 CAD 编辑/保存/重开、工程批准和 DWG 首发范围决定仍 pending，与下述技术缺陷分别记录。

上轮报告按原字节归档为 docs/reviews/B02-rereview-2.md，SHA-256 **53d50436a485f36117834461a4278809da9cf6a0029067a8bcc1947c8e361260**。新证据仅在 docs/evidence/B02-rereview-3/。只修改本报告、上轮归档和本轮证据；未修改业务代码、测试、执行报告、冻结候选、格式决定及编排记录；未运行 ODA/真实转换器、未操作真实 CAD、未借用其他项目授权、未代签批准，未进入 B03。

## 对象与绑定

本地交接 HEAD 55191441bf574b327ddaa3458e923cc8b89cfc60，实际开始 HEAD 3715f5ffed3acf016c897f8b821bb93019c09f33（其后差异为调度文档）；远端开始 HEAD 979cf98bb048d1527f17177b4f2f16d3cd5464f8。两端均为 codex/b01-foundation。独立源码契约 SHA-256 为 **08791e96eb0e9143646edf2428526fa6b8ddd632dede9c4091c73706427a999a**；原始快照、两端最终源码条目相同，不机械否定纯文档 HEAD 变化。

冻结目录：docs/evidence/B02-fix-3/candidate/。

| 文件 | SHA-256 |
| --- | --- |
| candidate-manifest.json | ede33aba47e52fd101826fec473f5af8b953389e52856e82d5de13ce5158af4b |
| heater-sample.dxf | 5984555dd8da5bdec572e3cd9b9fcd8de29e6df38d6c94b37c364ef6d32eceea |
| heater-sample.pdf | 2590306e3da7f483fef051d7865cdfc0d25f069e601c90a63d1fa934c19367b5 |
| reference-difference.pdf | bc8b3abfbc9757ca023c5fadfe4f68036fd4aae903c645a0124b728fd5a0b2b3 |
| drawing-pages.json | 676f98c07e7687478bec48e851fe58590e001732ea01435c725242c2fdc58739 |
| reference-measurements.json | 03ce1cad435a9aeb39bbaf6bf993458b970cf03f3e709181ef7f9090d5aebaee |

模板 DXF hash 仍为 944dcd371bd06c07670e735801fc57948d1a2d3345d361738368a41ce45e05f1。两端各自保护清单核对本地 958、远端 959 个既有文件，全部字节不变；原有 state/events 差异分别保留。全文件 hash、路径映射见 evidence-index.json；两端内容提交验真与干净状态见单独提交的 git-handoff.json。

已读取计划、B02、C02/C05/C06/C07、需求、基线、B01 执行/认可事实、本轮执行报告、进度与历史复审，检查实际实现、修复 diff 和测试。未发现适用 AGENTS。生成、变异和合成政策分支仅在隔离 Git 副本或本轮证据目录进行。

## 独立执行

| 验证 | 实际结果 |
| --- | --- |
| 原注册默认 B01：python scripts/verify_batch.py B01 --report-dir docs/evidence/B02-rereview3-b01-current | **0 / passed**；53 contract、46 planning，ECMAScript 与隔离 wheel 安装均退出 0；十项检查完整 |
| 原注册默认 B02：python scripts/verify_batch.py B02 --report-dir docs/evidence/B02-rereview3-b02-current | **2 / blocked**；42 格式测试、141 总回归通过，0 skipped；DXF/PDF probe 0；真实 blockers 仅 human-gate-0、check-format-gate |
| 重新采样真实 before/after 外部边界 | 两条 CLI 退出 0，同一严格验证器再次确认 passed / unchanged |
| 三个实际 DrawingPage | C02 模型与共享语义入口通过，单页/合并 DXF 原生尺寸、12 个箭头保留 |
| 原十类 DXF 负例 | 单位、丢尺寸、显示覆盖、非矩形、视口比例、尺寸倍率、视口旋转、纸宽、文字对齐、删图框，**10/10 拒绝** |
| 上轮字体/缓存反例 | arial 文件、DIMSTYLE→Standard、缓存 999、只改缓存位置均拒绝 |
| PDF 反例 | 错单页、单页 x+100 mm、合并第二页 x+100 mm，各自重 hash 后完整 probe 均 **1 / failed** |
| 政策矩阵 | 原 11 项函数矩阵随 planning 回归运行；另独立重复现有六次 B99 CLI 矩阵，pytest 通过，六个子进程结果见 reviewer-cli-matrix.json/xml/log |
| 当前 B01 依赖 | 新鲜原始绑定副本正例通过，12 个变异全部 blocked；另一副本完整 B02 裁剪摘要反例退出 2，明确 dependency-0 阻断 |
| Windows 完整回归 | 首次 **140 passed / 1 failed，退出 1**；单例重跑 1 passed，完整重跑 **141 passed，退出 0**，保留首次现场 |

远端真实根 .venv：Python 3.12.16、PyMuPDF 1.28.2、ezdxf 1.4.5、fontTools 4.68.0、pypdf 6.21.4、Matplotlib 3.11.2、pydantic 2.14.3。service/uv.lock SHA-256 为 7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60。只读 .tools/uv sync --project service --frozen --check，显式 UV_PROJECT_ENVIRONMENT=根目录/.venv，退出 0、检查 39 包、Would make no changes。未以临时 PyMuPDF 环境冒充服务环境。

独立渲染并目检源 PDF 三页、候选三页、差异 PDF 全部 11 页和负例；三个单页与合并对应页栅格逐像素相同。普通文字在实际 PDF 可见轮廓及独立 CAD 轮廓两种表示下，均未发现图框穿越或相互碰撞。F03 长边引线/尺寸侧别、F07 只读分离、F08 C02 修复保持有效。最终只读封存检查确认隔离副本 candidate/template 与原根逐文件相同，12 个箭头实际 PDF 纸面边界相对独立 SOLID 顶点最大差 0.00001724 mm（sealed-facts.json）。

原始 argv/cwd/退出码/日志见 results.json、mutation-results.json、policy-results.json、final-checks.json、dependency-original-results.json、supplement-results.json、windows-validation.json。受控假记录证明分支可达性，不是实际许可、转换或人类签收。

## F01–F09 处置

| 项目 | 结论 |
| --- | --- |
| F01 | 原字形短笔画错配已修；三页映射与未知说明有效，差异表仍跨行/列，未关闭。 |
| F02 | 原主要宽度问题改善；实际 PDF 与独立 CAD 的普通文字位置及 MTEXT 字距仍超 0.1 mm，未关闭。 |
| F03 | 原长边引线、尺寸侧别及冲突修复有效。 |
| F04 | 上轮字体/缓存指定反例已拒绝；有效显示属性仍漏检，未关闭。 |
| F05 | 原十反例、错页、单页/合并平移均拒绝；缓存同步位移及箭头比例仍误放行，未关闭。 |
| F06 | 精确 DWG、人员/时间/版本/动作绑定及 runner 状态分支修复有效；假 verified 可贯穿完整 required 分支，未关闭。 |
| F07 | 原候选和模板全部保护文件字节不变，只读分离有效。 |
| F08 | 实际三页公开 C02 语义有效。 |
| F09 | helper 日志/超时/进程组/旧输出及填充垃圾防线有效；capabilities 身份与真实执行证明不足，未关闭。 |
| B01 新模式 | 原摘要完整性绕过已关闭；真实 B01 重跑通过，原始当前绑定及历史唯一认可保留。 |

## 仍须修复

### F01 / P2：差异表状态文字跨行、跨列

位置：scripts/build_format_candidate.py:145，表格字号、换行和固定行高。

三页各 21 条候选图框线，4 条一对一完整长度匹配/重排、17 条候选未匹配；源未匹配条数 51/51/61。匹配长度比 0.9924–1.0172，不再将约 0.17 mm 字形笔画配作 200 mm 图框。外底/右/上差分别 0.986629/0.851027/1.184116 mm，明确标 relayout；frame-0 横向近零也同时列端点差 2.170745 mm，没有伪称重合。三页各 41 条固定/动态/技术文字值完整相符，源为轮廓而明确 unknown。这些修复成立。

但 11 页差异 PDF 的 candidate_added_or_source_deleted 状态折成两行，行高仍约 17.4 pt，FontProperties 又使实际字号成为 10。独立可见字形轮廓测得 **102 次状态 span 穿过水平单元格边界**，目检也可见侵入相邻列。例：第一页 candidate_added_or_s 的 bbox [296.0375,154.8782,402.8120,164.2382] 穿过 y=155.544 行界。原长字段名已能放下，不沿用旧越界结论。

源未匹配线原始段仅在 JSON，PDF 表主要列候选信息，缺源端点/未匹配源行。应按实际字号和换行计算行高，并补可读的源/候选/未匹配对应展示，保留已正确修复的数值匹配。证据：supplement-results.json 的 mapping、difference_status_border_crossings，visual/ 下差异全页及联系表。

### F02 / P1：实际可见字形位置及 MTEXT 字距仍超过 0.1 mm

位置：service/src/heater_drawing/drawing/pdf_renderer.py:84、text_metrics.py:103。

显式注册锁定 NotoSansCJKsc-Regular.otf，hash e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322，ezdxf PostScript 身份核验相同。PDF 提取不透明填充路径操作符，以 fontTools BoundsPen 重算 Bezier 极值，排除透明检索文字并按实体非空字形数分组。独立 CAD 用 ezdxf text2path；单行缓存 MTEXT 先经 MTextExplode 再测。每页 41 TEXT＋2 缓存 MTEXT＋4 箭头，分别完整消耗 290/296/302 个不透明填充。

最终每页最大边缘误差 **0.125479 / 0.203965 / 0.240234 mm**。CX-26“吕鑫”横向偏移 0.156618 mm；KX“中国科学院微小卫星创新研究院”偏移 0.171897 mm，“KX-11”偏移 0.122785 mm。前两者宽度已几乎完全一致，不能再归咎于上轮旧宽度问题。缓存尺寸 25/30/50/100/300 最大边缘差分别约 0.125479/0.189727/0.203965/0.240234/0.240228 mm；100 可见总宽仍小约 0.186881 mm。

应统一 TEXT/MTEXT 的 CAD 对齐、advance/字距、基线和锚点，以独立参考测量全部字形及尺寸，不能只让验证器与自身 renderer 一致。这是独立软件 CAD 解释，不冒充真实 AutoCAD 验收。正常箭头数量/几何和普通文字碰撞检查有效，但不能消除已测超差。

最终证据 visual-metrics.json、visual_metrics.py。保留的 visual-metrics-conservative-bounds.json 是早期 MuPDF 保守矩形结果，已被精确极值结果取代；不以其额外假超差提出问题。

### F04/F05 / P1：同步移动缓存与锚点可通过完整 probe；有效显示属性仍漏检

位置：service/src/heater_drawing/drawing/readback.py:104、:232、:332；scripts/probe_formats.py:91、:176。

原 arial、DIMSTYLE→Standard、缓存 999 和只改缓存 insert 均已拒绝。但新保存的反例仍被 inspect_dxf 接受：TEXT 实体 oblique=40°；缓存 MTEXT rotation=45°；缓存 insert 与 DIMENSION.text_midpoint **同时 x+20 mm**；箭头 INSERT xscale/yscale=0.1。STYLE 默认 width=0.3、oblique=40°也未拒绝，但默认值可能被实体覆盖，故不单据此声称当前页面必定改变。

最强反例复制真实候选，只改第一页缓存与 midpoint 同步 x+20 mm，重生成该单页 PDF/PNG、合并 PDF、刷新 manifest hashes，**实际完整 probe 退出 0 / passed**。尺寸文字明显离开原间隙；汇总 DXF仍是原件，单页/汇总该项不一致也未被发现。当前比较两个可变字段，PDF canonical 又从同一错误单页 DXF 重绘，故可同时证明错误图与自身相同。

应从规划/尺寸几何独立推导缓存位置，核对 rotation/attachment、有效倾斜/样式、箭头真实几何及大小、尺寸文字碰撞和单页/汇总一致性。统计两个 SOLID 或比较同步改动字段不能关闭这一类缺陷。保留已通过的错页/整页平移/旧字体拒绝能力。

证据 mutation-results.json、dxf-mutations/、cache-both-full/、cache-both-full.log、visual/cache-both-position.png；原候选未改。

### F06/F09 / P1：改名 Python 与垃圾 DWG 被认作 verified，完整 required B02 退出 0

位置：service/src/heater_drawing/drawing/dwg_adapter.py:200、:232，以及 gate/runner 对能力记录的消费路径。

有效改进：把回转加热器移 x+1000 mm 已变为 available_unverified；普通 Python 旧文件名被拒绝。DWG gate 对无关输出、缺操作人、未来操作、错误版本和缺动作均退出 2，精确绑定有效。旧 runner 硬编码矛盾也已消除。

仍可把真实普通 Python 复制并改名 ODAFileConverter，**副本从未执行**。其 hash 与实际 Python 相同：23bc148d2b48964b621c5561ff2b81c1d9c7b717967a7491efbf12f4304882b5。ELF 头＋basename 通过原生身份判断；自制版本回执及双向命令日志明确写 COUNTEREXAMPLE / NO ODA RUN，正确绑定实际候选输入、其字节复制的回转 DXF，以及 **AC1032＋2048 个 x 的垃圾 DWG**，capabilities 仍给 **verified_evaluation_only**。

helper 会拒绝该低熵填充，capabilities 却不执行同样检查；自填路径/hash/argv/版本及非空日志不能证明执行过转换。配上明确标为合成、结构完整且精确绑定垃圾 DWG 的 CAD 记录，**完整原注册 B02 required 分支实际退出 0 / passed**。这次没有任何转换/CAD操作，合成记录绝不代表实际授权或人类验收。

| 完整原注册 B02 独立政策分支 | 退出码 / 状态 |
| --- | --- |
| 合成 postpone | 0 / passed |
| pending | 2 / blocked |
| postpone＋矛盾 verified | 1 / failed（gate 通过，runner 拒绝矛盾） |
| required＋未验证 | 1 / failed（gate blocked） |
| required＋改名 Python/垃圾 DWG 假 verified | **0 / passed，错误放行** |

五次完整 B02 子进程使用真实冻结候选和原业务/测试；仅隔离副本设置合成批准/决定和 registry hash，重新真实采样边界、运行 B01=0、提交副本专用 B01 绑定。因 registry 变化其指纹为 40a01b…，不得冒称原始批准。另六次 B99 CLI 是既有受控 fixture，不替代这五次完整 B02，也不是实际转换正例。

应可靠识别真实程序/版本，把运行时生成的确切命令、输入输出及回执绑定到真实执行，垃圾 DWG 不得 verified；basename/ELF＋自描述 JSON 不足。保留默认禁用及范围待定规则。本轮不授权去运行 ODA。

helper 回归有效：exit 7 的 stdout/stderr 各 6001 字节完整；正确 0.15 s 超时保留两流各 12 字节，Linux 子进程 sentinel 未出现；旧输出、无输出、普通垃圾、header-only、低熵填充拒绝。首次审查 timeout 脚本有 SyntaxError，留档但不作为超时证明；真实超时见 supplement-first-run.json/supplement-results.json。重复 header-only 补测遇到旧文件，实质 header-only 拒绝取第一次补测。

证据 policy-results.json、policy-inputs/、policy-*/、gate-cases/、final-checks.json、helper/。改名可执行副本只在 /tmp，未执行、未归档入 Git；代码与真实 Python hash 可重建反例。

### Windows / P2：时间戳变异使用当前时钟导致不稳定

命令 .venv/Scripts/python.exe -m pytest -q tests/contracts tests/planning tests/formats 首次退出 1，唯一失败为 test_incomplete_or_forged_boundary_is_blocked[changed_baseline_timestamp]（约第 573 行）。保存现场 before/after checked_at 完全相同：2026-11-07T16:11:38.058504+00:00。fixture 后立刻 datetime.now() 恰在同一时钟刻度，没有真正变异，却期待 blocked。

单例及完整重跑均通过。这是变异用例不确定性，不能据此称校验器接受了真正改变的时间戳。应以明确偏移构造不同时间；保留首次失败，不只报绿色重跑，也不因此否定真实边界正例。

证据 windows-regression.log、windows-boundary-first/、windows-boundary-targeted.log、windows-regression-rerun.log、windows-validation.json。

## B01 当前依赖新模式：原技术绕过已关闭

当前原始 docs/evidence/B02-fix-3/b01-runner/summary.json SHA-256 为 **1d01759cc4d2e471b42e88780c42badacbf33bc3fffb1e28c0db3efee7821181**，source HEAD 76e56bfff504621908dab09e171cc75982f2d720；受控 b01-acceptance.json hash **bf4ba720c57d82970e4d5869760940dafc1f144f11e651e4c779faf9063b15d2**。历史唯一认可 B01-fix-2-r2/summary.json hash 仍为 **fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0**，未被当前报告取代或伪造。

完整审计当前报告四项必需命令、十项检查、边界/输入/产物/原始日志后，原始环境默认 B01 实际重跑通过，默认 B02 接受既有当前报告，说明纯文档 HEAD 未被误拒。新鲜独立副本使用原始 source 08791e…、原摘要和 Git HEAD 绑定，正例通过；删命令、argv=true、删边界 check/input、错 source/status、未来/过期、错日志/输入/产物 hash 共 11 项全部 blocked；同步重写工作区 binding 的第 12 项被 Git HEAD blob 比对拒绝。另一独立原始副本裁剪摘要后，完整 B02 退出 2，明确 exact report/source binding failure。

mutation-results.json 早先依赖部分实际用了政策合成绑定 40a01b…，不作为原始报告正例；dependency-original-results.json 才是原始绑定的 13 项结果。补测第一次遗漏 ignored dist wheel，正例因缺文件 blocked，dependency-original-first-run.json 留档；复制原根 dist 后重跑，正例及 12 拒绝均符合预期。临时改写仅在副本，原报告/绑定受保护清单核验。

历史认可保留；当前影响由当前指纹、完整真实报告、Git 控制的确切绑定支持，本轮又实际运行 B01 和真实边界。该技术项关闭不代表 B02 通过。

## 交接边界

下一轮修复差异表可读性、独立 CAD/PDF 对齐与 MTEXT 度量、有效显示/缓存/箭头验证、转换器 verified 证据可信性，并消除 Windows 时间戳用例不稳定；保持本轮已通过回归。真实 CAD 验证、工程批准和 DWG 首发决定仍须由实际授权及人类流程完成。

本报告和证据在两独立仓库分别有意提交，保留各自调度记录。索引绑定报告/归档/本轮材料，Git 交接记录另行提交避免自引用。**FAIL，止于 B02，不进入 B03。**
