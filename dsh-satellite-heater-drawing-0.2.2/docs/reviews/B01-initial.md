# B01 独立验收报告

**结论：FAIL。** 环境可在补充激活步骤后按 frozen 锁恢复，材料也正确；但 README 的完整恢复流程不可直接复现，runner 存在真实假成功，Python/JSON Schema 的契约行为不一致，错误枚举、revision hash 绑定及边界变化证据尚未满足 B01 硬门槛。原有 20 项测试和交付 summary 的 passed 不能消除以下问题。应退回原 B01 执行聊天修复，未获重新验收通过前不得进入后续 Batch。

审查日期：2026-11-07，Asia/Shanghai。审查只新增本报告与 `docs/evidence/B01-review/` 独立证据；没有修改业务代码、既有测试、执行报告、执行者证据或 `docs/orchestration/state.json`，没有开展后续 Batch。

## 1. 依据、身份及版本核对

- 已读取适用祖先路径并搜索项目内 `AGENTS.md`。本地 `C:\` 至项目路径、远端 `/`、`/data`、`/data/qmh`、父项目与本项目均未找到适用 AGENTS；未据此增加代理或委派工作。
- 已读取 `docs/orchestration/review-prompt.md`、`docs/plan.md`、`docs/progress.md`、`docs/batches/B01.md`、`docs/contracts.md`（重点 C01/C02/C07）、`docs/reference/{requirements,project-baseline}.md`、`source-files.json` 及 `docs/reports/B01.md`。B01 无前置开发 Batch。
- 本地调度根：`C:\Users\HUAWEI\Documents\ChatGPT\矩形加热器插件\heater-drawing`。实际本地 Git 顶层是其父目录 `C:\Users\HUAWEI\Documents\ChatGPT\矩形加热器插件`，并非误把别的仓库当本项目。
- 权威源码/执行证据根：`5090-qmh:/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing`。
- 审查开始本地：分支 `codex/b01-foundation`，HEAD `7d62d39b825f7aa644103f47ae1883c1cdfe680e`；`git status --porcelain` 为空，`git diff --check` 退出 0。
- 审查开始远端：分支 `codex/b01-foundation`，HEAD `f21fd306cb01499c8e0de49963e6a28d58859e2b`；`git status --porcelain` 为空，`git diff --check` 退出 0。
- 实际检查 `git log`、`git show --stat 6ee87c1` 和 `git diff 6ee87c1 HEAD`：远端 `6ee87c1e9bbb5021f6124180bcb3ca8132b75781` 后只有交付文档/证据提交；没有隐藏的后续业务源码修复。本地 `4c3d8cba4b655859b4dbcfb2ca09ede9fa0d54ba` 后只修改调度文档。
- 对远端交付的 54 个非 orchestration 跟踪文件逐一 SHA-256 比对，本地全部一致；仅 `docs/orchestration/events.md` 与 `state.json` 存在预期调度差异。记录在 `docs/evidence/B01-review/local-remote-comparison.json`。

独立读过全部业务 Python、runner、边界脚本、registry、既有测试、pyproject、锁文件、5 个 Schema/OpenAPI、README、材料清单与 expected；结论来自代码及下列独立反例，不来自执行者总结。

## 2. 实际命令、验证结果与证据

独立复现入口（在远端根）：

```bash
.venv/bin/python docs/evidence/B01-review/independent_probe.py /data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing
.venv/bin/python docs/evidence/B01-review/supplemental_probe.py /data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing
```

两次探针最终退出均为 0，表示独立取证程序完成，**不表示 B01 通过**。每个子命令的实际 argv、cwd、退出码和日志 SHA-256 在 `results.json`；补充命令/结果在 `supplemental-results.json`。新建隔离恢复目录为 `/tmp/heater-b01-independent-oiegr9o7/`，源码来自远端 `git archive HEAD`；人工构造的 registry、缺失门槛及变更模拟仅在该隔离副本进行。审查工具 JSON Schema 4.26.0 安装在独立 `/tmp/.../audit-libraries`，没有加入项目依赖或改变锁文件。

| 验证 | 真实结果 | 证据 |
|---|---|---|
| 原远端 `.venv/bin/python -m pytest -q tests/contracts tests/planning` | 退出 0，20 passed | `existing-tests.txt` |
| 原远端 runner B01，独立 report-dir | 退出 0，summary passed；这只能复现当前 runner 的判断 | `runner-current/summary.json`，日志另保存同 hash 的 `.txt` 副本入库 |
| 全新 managed Python、空 venv、空 uv cache；`uv python install 3.12`、`uv venv .venv --python 3.12` | 均退出 0；uv 0.13.7、Python 3.12.16 | `fresh-python-install.txt`、`fresh-venv.txt` |
| 完全照 README，未设置 VIRTUAL_ENV 的 `uv sync --project service --frozen --active` | 退出 0，却创建并安装到 `service/.venv` | `readme-frozen-sync.txt` |
| 紧接 README 的根 `.venv/bin/python -m pytest ...` | 退出 1，`No module named pytest` | `readme-root-tests.txt` |
| 显式令 VIRTUAL_ENV 指向根 `.venv` 后再次 frozen sync、运行两组测试 | 均退出 0，20 passed；证明依赖本身可按锁重建 | `activated-frozen-sync.txt`、`fresh-root-tests.txt` |
| 全新副本构建 wheel，另建 wheel venv 并安装；从源码目录外 import | 构建/安装/资源验证均退出 0；模块确实从 wheel venv 的 site-packages 导入 | `fresh-wheel-build.txt`、`wheel-install.txt`、`wheel-resource-check.txt` |
| 外置资源 root，未配置 root/缺模板/有 Schema | 前两项拒绝，Schema 目录可定位；未伪造 B02 模板 | `wheel-resource-check.txt` |
| 实际交付 wheel 再安装并 import 核心模型 | 退出 0；交付 wheel hash 与报告一致。与本次新 wheel 的差别是源文件末尾空行，无业务语义差异，不判为 wheel 失效 | `supplemental-results.json: delivered_wheel` |
| 10 个原件与 source-files、manifest 的大小/hash | 全部一致 | `results.json: observations.originals` |
| 实际原始 ZIP 的 10 个条目，与本地 fixture 独立比对 | 退出 0，10/10 大小/hash 一致 | `original-zip-check.json` |
| 直接读取真实 Excel，逐格比对 expected 全部 51 个动态值 | 仅第 2、3、4 行有业务值；expected 恰好三行；51 项均一致；O3=郑玲 | `results.json: observations.excel` |
| UUID、未知字段、十进制、schema_version、行号与 Schema 行为 | UUID 非法值拒绝；17 字段和快照匹配；但有下述 F03/F05 差异 | `results.json: observations.model_schema_comparisons` |
| 修复后的行号正则 | 2、9、10、19、20、99、100、1048576 均在 Python/Schema 接受，未发现原先十位行号遗漏复发 | 同上 |
| generic canonical JSON/hash | UTF-8、中文、排序、紧凑分隔符和手算 SHA-256 一致；NaN 拒绝；尚不能证明 revision 内容绑定 | `results.json: observations.canonical`、补充结果 |
| runner 真失败、零测试、缺报告、缺人工、未登记项 | 分别退出 1/1/2/2/2，未假成功；缺可执行文件退出 1，错误类别未按 C07 分成 blocked | `results.json: observations.runner` |
| runner 混合 passed+skipped、空命令、存在但 failed 的依赖报告 | 三者均退出 0/passed，实质假成功 | 同上 |
| dependency report 内容 hash | 内容改变 hash 确实改变，但不校验依赖是否通过及适用版本 | 同上 |
| source boundary 真实前后采样 | 5 个参考仓库、6 个文件状态一致；没有修改/回滚参考项目 | `boundary-before.json`、`boundary-after.json` |
| source boundary 外部变更模拟 | 同一个已脏文件从内容 A 改成 B，采样除时间外完全相同，仍断言为外部工作 | `results.json: observations.boundary_simulation` |
| runner 对 status=failed 的边界证据 | B01 仍退出 0/passed | `supplemental-results.json: runner_accepts_failed_boundary` |

原始 ZIP 独立命令（本地根，退出 0）：

```powershell
python docs/evidence/B01-review/original_zip_check.py . 'D:\小卫星\插件\矩形加热器自动出图案例.zip'
```

关键 hash：锁文件独立恢复前后均为 `0fc754a31e7255ebe8ce2d662c9c20a707c32ada732bb0c8710e00d7e33ecf27`；实际交付 wheel 为 `4364ec9debc951b4e50a754cdaa048e3a49ad04b3c9b2adca61ca290477b560c`；此次重建 wheel 为 `34776f78545492a60d40183a85714ec0e44e0d2694ebf2d0faf58609a343a4c5`；用户原始 ZIP 为 `c4458b660cd5bdf0aca1a10d424ea81bd9c6bd3fe7af34ca00d871e1ae62a8bc`。原执行 summary 记录的测试日志、各 Schema、锁文件和 wheel 在远端都存在且 hash 匹配，未发现证据文件被替换。

## 3. 必须修复的问题

### F01（P1）README 无法从干净环境重建并执行所列验收

路径：`README.md:20-21`、验收代码段；对应 `scripts/verify_batch.py:118-120`。

触发：从无 VIRTUAL_ENV 的新 shell 完全照 README 创建根 `.venv` 后执行 frozen sync。`--active` 没有活动环境可选，uv 实际创建 `service/.venv`。下一条根 Python 命令缺 pytest 并退出 1。即使补上激活，README 仍未说明构建 wheel，而 runner 硬要求 dist 内恰有一个 wheel；独立移除隔离副本中的 wheel 后，20 项测试通过但 runner 退出 1（foundation-files、wheel-contents 失败）。

影响：B01“根 README 能使下一聊天重建环境”和全新隔离恢复门槛不成立。

修复要求：明确激活根环境或显式固定目标 Python/VIRTUAL_ENV，补全从跟踪文件恢复到 wheel 构建、资源布局和统一 runner 的完整命令。恢复保持 frozen，不重新求解锁。

修复后验证：新空目录/新 venv/无 VIRTUAL_ENV，逐字执行 README；根 Python 能 import 全部依赖，根路径测试与 B01 runner 成功；记录解释器实际路径、锁 hash 未变、wheel 安装及资源定位。不得沿用现存 dist 或 service/.venv 掩盖缺步骤。

### F02（P1）runner 在必需验收被跳过、空 registry 和失败前置下假成功

路径：`scripts/verify_batch.py:43-52,153-160,203-215,263-276`、`tests/planning/test_runner.py:32`。

触发及复现：

- 真实 pytest 文件含 1 passed、1 个必需测试 skipped，pytest 退出 0；runner 返回 passed/退出 0。既有测试甚至明确断言 `12 passed, 1 skipped` 应通过，与 C07“必需测试被跳过不可 pass”冲突。
- 已登记 spec 的 `commands=[]`，无任何测试/人工证据，runner 仍依靠 B01 文件存在性返回 passed/退出 0。
- `dependency_reports` 指向真实存在的 `{"status":"failed"}` 报告，runner 只算文件 hash，仍 passed/退出 0。没有通过状态、源码时效/变化影响检查或绑定既有验收基线；hash 改变虽可记录，却不会阻断。
- 缺可执行程序被记为 technical failure/退出 1，未遵守 C07 缺环境退出 2 的类别。

影响：通用验收入口不能证明全部必需项/前置门槛满足，可以把缺能力、缺测试和失败依赖描述为通过。

修复要求：必需测试的 skip 必须阻断；若允许非必需 skip，需逐项明确登记，不能只看总 passed 数。拒绝空或没有任何有效必需验收的登记项；解析并验证前置报告状态、完整证据及适用源码/契约，内容变更时执行影响判断/重验，不能只记录当前 hash。区分技术失败和缺环境，所有出口都写完整 summary。

修复后验证：使用真实 subprocess 覆盖失败、零收集、全 skip、混合 skip、缺测试文件、空命令、缺 executable/包、缺人工、缺依赖、failed/blocked/陈旧/内容变化的依赖报告及正常成功；分别断言 C07 的 0/1/2 及 summary，不得以伪造 pytest 文本代替主要验证。

### F03（P1）模型与共享 JSON Schema 的行为一致性没有建立

路径：`service/src/heater_drawing/domain/models.py:22-28,113-161,273-291,331-336`，受影响的 Schema 定义和 `tests/contracts/test_models.py:119`；另见 `service/src/heater_drawing/config.py:59`。

已复现：

- `HeaterRow.schema_version=true`、`Scale.numerator=true` 在 JSON 输入中被 Pydantic 接受，Draft 2020-12 Schema 拒绝。`ServiceConfig(schema_version=2,...)` 也接受，schema_version=1 未固定。
- `width_mm="1٢"`（末尾阿拉伯数字 ٢）被 Pydantic 的 Unicode `\d` 接受；相同已导出 pattern 在实际 Node/ECMAScript 中拒绝。`"1\n"` 被 Python jsonschema 的 pattern 接受，Pydantic 拒绝。快照 JSON 等于 `model_json_schema()` 不能发现正则引擎差异。
- `row_id=Sheet1:3` 配 source 第 2 行、Scale 分母 2 配 label `1:5`、row Issue 缺定位、system Issue 却 skippable、artifact `../escape.pdf`：Python 拒绝而公开 Schema 接受。
- 更直接的错误行号问题：Issue 的 `row_id=Sheet1:2,sheet=Sheet1,excel_row=3` 在 Python 与 Schema 都接受。修复了行号正则覆盖并不等于保证错误定位一致。

影响：不同消费端对同一 v1 payload 作不同判定；Schema 消费者能放入错误行定位、错误跳过和不安全产物路径，不能以“已双向测试固定”交接。

修复要求：数字使用双方一致的 ASCII 十进制语法及严格类型，明确完整字符串匹配；整数常量禁止 bool，配置版本固定 1。对 Issue 条件必填、非 row 禁 skip、安全路径等可表达约束补入 Schema，并保证 Issue 的行位置互相一致。JSON Schema 标准不能直接表达任意跨字段字符串拼接/相等比较的部分，必须在契约中明确结构校验与强制共享语义校验的边界，提供同一语义验证入口和消费者要求；不能声称自动导出的 Schema 已覆盖这些校验，也不能为追求快照一致删除 Python 安全校验。

修复后验证：实际 JSON 输入，在 Pydantic、独立 Draft 2020-12 validator 和 ECMAScript 实现中运行有效/无效样例矩阵；覆盖上述反例及未知字段、非法 UUID、0/负数/NaN/Inf/bool、行 2/9/10/19/20/99/100 和错误行位置。显式标记结构层及语义层预期；单纯快照 equality 不足。

### F04（P2）要求固化的错误编码仍是任意大写字符串

路径：`service/src/heater_drawing/domain/models.py:146,295`、`schemas/error.schema.json`、`schemas/revision.schema.json`。

触发：`TOTALLY_UNREGISTERED_ERROR` 作为 Issue.error_code 或 ErrorResponse.error.code，Python/Schema 都接受。实现只有字符串 pattern，没有 ErrorCode 枚举；现有测试也未核对错误编码集合。

影响：不满足 B01 §4“错误编码必须固定、形成 enum 和跨 Python/JSON Schema 一致测试”，后续 Batch 可各自拼写，前端及报告无法可靠消费。

修复要求：先固化本批/既定契约实际定义的最小错误编码集合（包含契约已使用的 WORKER_INTERRUPTED 等适用编码），Python/Schema/OpenAPI 共用并写明受控扩展规则；无需提前实现 B03/B06。

修复后验证：枚举中每项能跨层往返，未知/拼错/大小写不符值均拒绝，Issue 与 HTTP error 的集合关系明确并有测试。

### F05（P2）比例契约允许需求明确禁止的放大比例

路径：`service/src/heater_drawing/domain/models.py:82,113-123` 及相应 Schema 的 requested_scale/Scale。

触发：`requested_scale="1:0.5"` 或 `Scale(denominator="0.5",label="1:0.5")`，Python/Schema 均接受。

影响：R01 规定首版不支持放大比例，而 1:0.5 是放大 2 倍；这不是尚未实现的 Excel parser 才应处理的格式差异，当前共享规范值/Scale 已接纳不支持的数据。

修复要求：在规范值及 Scale 契约中限制分母 ≥1，同时保留普通尺寸所需的正小数范围；不要把所有 PositiveDecimalString 的下界统一改成 1。

修复后验证：1:1、1:1.5、1:2 通过；1:0.5、1:0、负值、NaN/Inf 拒绝；输入字符串、对象与 Schema/语义校验行为一致。

### F06（P1）只实现通用 JSON hash，没有冻结可复核的 revision hash 输入绑定

路径：`service/src/heater_drawing/domain/models.py:196-211,315-328`、`tests/contracts/test_models.py:109-116`。

事实：只有接受任意 Any 的 `canonical_json_bytes/canonical_sha256`；Revision.revision_hash 只约束 64 位十六进制。没有 revision 专用的规范载荷/构造或验证入口，也没有对 C01 所列覆盖项的测试。独立构造 Revision，改变 source_sha256、template_hash、font_manifest_hash、output_profile、skipped_row_ids，仍可携带完全相同的全零 revision_hash；直接把 Revision 传入 generic hash 则 TypeError。通用 hash 的排序测试通过只证明序列化工具有效。

影响：尚未规定哪些字段及规范表示参与 hash、如何排除自身/非输入字段，无法证明原值/规范值、最终比例、跳过原因和格式 profile 已被可靠绑定。把它留给后续聊天各自选择载荷不满足 B01 固化 C01 的任务。

修复要求：提供明确的 revision hash 输入结构/投影和服务端计算入口，说明 UUID/日期等值的 JSON 表达、自身 hash 的排除和必须覆盖的 C01 字段；创建/验证 Revision 的适用入口使用它。无需提前实现任务服务或数据库。

修复后验证：固定已知载荷与独立手算 hash；键序改变不影响结果；逐项改变源文件 hash、17 个 raw/values 值、模板/字体、最终比例、skip 行及原因、profile 都导致 hash 改变；省略必需覆盖项及无效数字不能静默生成有效绑定。测试 hash 的内容绑定，而非仅检查 64 字符格式。

### F07（P1）边界脚本不能如实观察已脏文件的新变化，runner 也不消费边界结论

路径：`scripts/check_source_boundary.py:49-91`，尤其固定 note；`scripts/verify_batch.py:119-120`。

触发：隔离模拟仓库的 tracked.txt 已有修改 A，采样后改成 B，Git HEAD 与 porcelain 路径均未变；除 checked_at 外报告完全一样。脚本只给六个固定参考文件算 hash，不记录其他 Git 可见脏内容的 diff/content hash。无比较基线，并无论实际原因都写“Dirty files belong to external work ... were not changed ... by B01”。另外把隔离副本的 source-boundary.json 换成 status=failed、missing 非空，B01 runner 仍 passed/退出 0，因为仅检查文件存在。

影响：B01 重点要求“只读且如实辨别外部变化”未满足。不能凭该报告宣称未覆盖既有用户改动；边界环境失效也不能阻止验收通过。

修复要求：保持对外部项目只读；增加足够的前后比较依据（HEAD、Git 可见差异内容 hash/必要文件 hash，妥善处理未跟踪项），区分未变化、观察到外部变化、归因未知和有证据的本批越界。不能无依据断言全部脏改动属于外部，也不能因并行外部变化自动回滚或要求别的项目保持不变。runner 应校验边界证据结构、状态、对应版本/采样与缺失项，不能只看文件名。

修复后验证：只在临时模拟仓库验证 clean、首次修改、同一路径二次修改、提交推进、引用文件变化、missing/error；确认变化被报告、外部变化不被误判本批越界、归因不明如实保留，外部文件字节及 Git 改动不被脚本改变。故障/缺失/陈旧边界证据不能让 runner 返回 passed。真实参考仓库再做只读前后采样。

### F08（P2）OpenAPI 快照给无前缀健康路由加上业务前缀

路径：`schemas/openapi.json:8-11`。

触发：全局 server `/api/heater/v1` 与 `/healthz`、`/readyz` 组合后表示 `/api/heater/v1/healthz`、`/api/heater/v1/readyz`，与 C04 明确的“无前缀”不一致。标记 not_implemented 不会改变 OpenAPI 路由解析语义。

影响：B01 交接的公开路由快照与已定义契约不一致，后续客户端/探针按快照生成会使用错误地址。

修复要求：对两个健康 operation/path 使用正确的 server 覆盖，或调整快照路径/servers 结构，使健康路由无前缀、业务路由保留统一前缀；继续标明未实现。

修复后验证：解析 OpenAPI 后枚举实际解析 URL，断言两条健康路由及所有业务路由与 C04 一致；不要求 B01 启动真实 HTTP 服务。

## 4. 剩余风险与复审要求

本次没有发现原件替换、O3 抄错或修复后的 10–19 行正则遗漏；Pydantic 正则在锁版本下可以加载和执行。不能把这些正向结果扩大为全部 Schema/业务门槛通过。独立验证也确认 wheel 的实际安装/导入能力，wheel hash 差异仅为空行，不另列阻塞。

B02 模板/字体授权、DXF/PDF、DWG 许可与目标 CAD 编辑、B03 Excel 解析、工程人工签收均未开展，不是本次 FAIL 的借口或替代证据。本批本来没有人工门槛，因此 human_decisions 为空并非问题；runner 对缺人工的阻断已有正向反例验证。

当前 runner 还仅按文件名检查 wheel 内容、按一个 O3 值检查 expected、按边界文件存在检查边界，无法持续代替以上独立验收。修复时应把本批硬门槛纳入真实、可复现的注册检查；不可通过删除安全约束、弱化契约、改期望为当前错误行为或把必要测试变 optional 来取得通过。

执行者应在原 B01 聊天处理 F01–F08，重跑原验收及真实反例，更新交付报告/证据和进度；再交独立复审。审查者本次不改上述交付文件和调度 state。

## 5. Git 与证据交接

审查新增范围严格为 `docs/reviews/B01.md`、`docs/evidence/B01-review/`。既有忽略规则只覆盖直接位于 Batch 证据目录的 `.log`；本次 runner 日志位于更深的 `runner-current/`，原始 `.log` 与同 hash `.txt` 副本均入库。证据目录内增加 `* -text` 属性以保留跨平台原始字节，没有新增 ignore 规则或丢弃取证结果。venv、wheel、下载缓存、依赖库和故障注入目录位于既有忽略目录或 `/tmp`，不入库；未修改或删除原交付成果。

开始状态和源码 HEAD 见 §1；新增取证期间 `status --porcelain` 仅出现上述审查目录/报告，`git diff --check` 退出 0。本地与远端分别提交审查报告和允许入库证据；文档提交不能在自身内容中包含自身 Git hash，提交后的第一轮确切 HEAD/分支/status/diff-check 记录在 `docs/evidence/B01-review/git-handoff.json`，随后仅提交该交接记录。最终文档 HEAD 可由各仓库 `git rev-parse HEAD`/`git log -1` 获取；最终两库 `git status --porcelain` 必须为空、`git diff --check` 必须退出 0。

独立证据完整同步在本地/远端同名 `docs/evidence/B01-review/`。后续复审应使用修复后的实际源码及新证据，不能复用本次执行者 passed summary 直接放行。
