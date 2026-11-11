# B01 F01–F08 独立复审报告

**当前结论：FAIL。** F01、F04、F05、F08 已解决；F02、F03、F06、F07 仍有影响 B01 验收的问题。独立复跑确认 59 tests、Node、隔离 wheel 及全新 frozen 恢复成功，但这些检查漏掉合法 Issue 往返失败、Revision 实例 hash 校验绕过，以及 runner 放行不完整/源码指纹失效的证据。应退回原 B01 执行聊天继续修复，不得进入 B02。

日期：2026-11-07（Asia/Shanghai）。初审逐字节归档为 [B01-initial.md](B01-initial.md)，SHA-256 `501b2ed823f7d5d46769807332195db33379627a584787bd9766888925459636`；原 `docs/evidence/B01-review/` 和修复者 `docs/evidence/B01-fix/` 均未改写。初审 evidence-index 的旧报告 hash 现在对应归档文件，原路径 B01.md 用于当前复审结论。

## 1. 审查依据与实际交付版本

重新检查祖先和项目内 AGENTS.md，无适用文件。读取 review-prompt、plan、progress、B01、contracts（含新增 C02.1–C02.3）、requirements、原审查、最新执行报告及 B01-fix 的 summary、边界、隔离恢复证据；检查实际源码差异、模型/Schema、runner、证据辅助函数、边界采样、wheel/Node 脚本和测试。没有委派其他代理，没有修改业务源码、既有测试、执行报告、初审/修复证据或调度 state，没有启动任何后续业务。

| 仓库 | 复审开始 HEAD / 分支 | status / diff-check |
|---|---|---|
| 本地 Git 顶层 `C:\Users\HUAWEI\Documents\ChatGPT\矩形加热器插件`，项目子目录 heater-drawing | `be9819f4707c8845419afa0c7b03c22a46be69e4` / `codex/b01-foundation` | porcelain 为空；diff-check 退出 0 |
| 远端 `5090-qmh:/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing` | `9b0c69dcad6b521e3002bcae25edfcac9b0becba` / `codex/b01-foundation` | porcelain 为空；diff-check 退出 0 |

实际核对远端 `804a9611a87f2945b22b21bffb195e66b9828bb5..HEAD`，只有报告/进度/修复证据变化，没有验收源码之后的业务改动。本地 `036974388adaeef06cd77337c8fadd68783af8ec..HEAD` 只有调度文档变化。逐一核对 101 个非 orchestration 跟踪文件，本地和远端字节 hash 全部一致。两端源码契约指纹均为 `d312da63298e2cdd94f73df81cdf636e6747294465c1c36153423554d1c83641`，对应实际修复源码；详见新证据 `mirror-check.json`、`results.json: source_entries/tracked_hashes`。

正式修复 summary 的 4 份日志、全部 input_hashes 和 artifact_hashes 在权威远端均存在且 hash 匹配，包括锁和 wheel。未发现修复者伪换这些文件；本次 FAIL 是实现/验收缺口，不是怀疑其运行了另一版源码。

## 2. 独立命令与结果

新证据根为 `docs/evidence/B01-rereview/`，已双端同步。可复现入口（远端项目根）：

```bash
.venv/bin/python docs/evidence/B01-rereview/recheck.py /data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing
.venv/bin/python docs/evidence/B01-rereview/additional_checks.py /data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing
```

两条取证脚本退出 0 表示取证完成，**不表示 Batch 通过**；脚本保存错误行为而不修业务。所有子命令的实际 argv/cwd/退出码/原始日志及 hash 见 `results.json`；每个 runner 反例的 registry、输入及真实 summary 保存在新目录。人工构造的 B99 只用于测试 runner，不代表实现或进入任何后续 Batch。

| 独立执行 | 真实结果 | 新证据 |
|---|---|---|
| `.venv/bin/python -m pytest -q tests/contracts tests/planning` | 退出 0，59 passed | `tests.txt`；全新环境另见 `readme-block-2.txt` |
| `node scripts/check_ecmascript_contract.mjs` | 退出 0，Node v12.22.9，failures=[] | `node.txt` |
| `.venv/bin/python scripts/check_wheel_install.py` | 退出 0，实际交付 wheel 安装到临时独立 venv，从 site-packages 导入，6 个外置 Schema 可定位 | `delivered-wheel.txt` |
| 独立 boundary before 和 after CLI | 两次退出 0；真实 5 仓库/6 参考文件完成比较 | `boundary-before/after.json` 和同名 `.txt` |
| runner B01，使用相同 4 个必需命令/内建检查，仅令 boundary 路径指向本次独立采样 | 退出 0、passed；当前正常路径可复现 | `independent-registry.json`、`runner-current/summary.json` |
| 从当前交付 HEAD 的 git archive 解包到新 `/tmp/heater-b01-rereview-cwsmhg36/fresh`，删除继承 VIRTUAL_ENV/PYTHONPATH，逐字执行 README 两个 bash 命令段 | 两段各退出 0；初始无 .venv/.tools/dist/service/.venv，最终根环境 59 tests、Node、wheel/资源、边界和 runner passed；没有创建 service/.venv | `readme-block-1/2.txt`、`results.json: fresh_initial/fresh_final` |
| 全新根解释器 import pytest/Pydantic/FastAPI/openpyxl/ezdxf/Matplotlib/pypdf | 退出 0，Python 3.12.16、Pydantic 2.14.3；路径确为新根 .venv | `fresh-root-interpreter.txt` |
| ASCII 小数、非有限数、bool、常量版本、行 2/9/10/19/20/99/100/1048576、比例、未知字段/错误码 | 修复涉及的这些反例按预期接受或拒绝；枚举三层一致 | `additional-results.json` |
| 10 个原件大小/hash；真实 Excel 51 字段与 expected | 全部一致；expected 三行，O3=郑玲 | `additional-results.json: materials/excel` |
| 手工按契约投影构造 JSON 并独立 SHA-256 | 与实现相同，`fce4bf353d3bd8485d5dbaf7f8ee5221604d3cf8816449c2ea6f93da12aa8afe`；说明专用投影/算法已建立 | `results.json: revision_known_projection` |
| 真 subprocess 的 fail/zero/mixed skip/空命令 | 分别退出 1，均 failed；初审对应漏洞已修 | `results.json: runner_cases`、`runner-cases/` |
| 缺 executable/包/人工、failed/blocked/超龄依赖、failed boundary | 分别退出 2，均 blocked | 同上 |
| 缺日志的依赖、失效源码指纹的依赖、无明细边界 | 全部错误地退出 0、passed | 同上，见下列 R02/R07 |
| 非行 Issue 的默认 JSON 往返、可变 Revision 实例、expected 顺序反例 | 仍违反契约，见 R03/R06 | `results.json` |
| 边界同路径二次修改模拟 | 能识别 diff hash 改变，unknown_external 归因，文件内容未被回滚；但空 baseline 仍通过 | `additional-results.json: boundary` |

本次冻结恢复前后锁 hash 均为 `9346337184b735a6a3332c28be844313f51e2ff95decf16ac85cbc3668a38a1b`；实际交付 wheel 为 `db06e8219940c62349a71cf9b90d685a2f7266ac6d8c76fb6ea05a7fb9661c2d`。隔离恢复未重新求解锁，未复用共享 venv，也未虚构模板或人工批准。

## 3. F01–F08 逐项结论

| 初审项 | 当前结论 | 依据 |
|---|---|---|
| F01 恢复与 wheel 步骤 | 已解决 | 完整 README 在全新目录逐字执行成功，根环境固定，锁不变，wheel/外置资源真实安装验证。 |
| F02 runner 失败、skip 与依赖 | **未完全解决** | fail/zero/skip/空命令及缺环境类别已修；依赖只核对报告自述，缺日志/失效源码指纹仍能 passed，见 R02。 |
| F03 跨层校验 | **未完全解决，存在相关回归** | ASCII、严格版本/布尔和共享语义边界已明确，原行号覆盖有效；合法非行 Issue 的 JSON 序列化却被结构层拒绝，见 R03。 |
| F04 错误枚举 | 已解决 | 13 个 ErrorCode 在 Python/Schema/OpenAPI 一致，未知编码拒绝，扩展规则已写入契约。 |
| F05 禁止放大比例 | 已解决 | 1:1/1:1.5/1:2 接受；1:0.5/零/负数/NaN/Inf 拒绝；普通尺寸 0.001 仍可接受。 |
| F06 revision hash | **未完全解决** | 新增专用载荷、构建及计算入口，字典篡改可拒绝；实例验证入口直接放行，且 expected 顺序可变而 hash 不变，见 R06。 |
| F07 边界只读/真实变化/证据门槛 | **未完全解决** | 采样已能捕捉同路径变化并如实保持未知归因；runner 接受无采样明细的边界、采样器接受空 baseline，见 R07。 |
| F08 OpenAPI 路由 | 已解决 | 根健康路由无前缀，业务路径保留 /api/heater/v1；Python 路由测试与实际快照核对一致，均标记未实现。 |

## 4. 必须修复的剩余问题

### R02（P1，续 F02）：依赖验收只查自述，引用证据与源码内容身份未核验

位置：`scripts/verify_batch.py:178-258`，尤其 224–255；`tests/planning/test_runner.py` 的合法依赖样本仅含 status/exit_code，不含真实日志与源码指纹验证。

复现：在独立目录复制真实 B01-fix summary，保留 passed、4 个 exit_code=0、checks、已匹配的 source_git_head/contract_version 和新鲜时间，再作两类单点改变；registry 绑定改变后的报告内容 hash，真实 pytest 仍作为必需命令运行：

1. 将所有 command.log 指向实际不存在的 `docs/evidence/B01-rereview/DOES-NOT-EXIST.txt`，log_sha256 改为全零。`dependency_missing_logs` 返回 **0/passed**。
2. 将报告 `source_contract_sha256` 改成全零，registry 明确登记应为当前真实 `d312...3641`。`dependency_stale_source_fingerprint` 仍返回 **0/passed**；该字段完全未消费。

证据：`runner-cases/dependency_missing_logs/summary.json`、`runner-cases/dependency_stale_source_fingerprint/summary.json`，输入报告/registry 与结果汇总均在新目录。内容 hash 变化本身确实能阻断，failed/blocked/超龄报告也能阻断；问题是“报告文件 hash 正确”仍被当成“引用证据完整、源码内容适用”。相同 Git HEAD 可以有不同工作树内容，单纯比较报告和 registry 中的 HEAD 字符串不足以证明版本适用。

影响：C07 仍可能把失去关键日志、内容已失效的前置验收放行。修复者声称的“证据完整性/源码时效检查”尚未成立，不能以新的 passed summary 替代独立核验。

修复要求：核验依赖报告引用的必要日志/输入/产物是否存在、hash 是否对应及记录是否完整；源码内容指纹必须与登记基线/当前适用范围匹配，或有明确的影响分析与重验记录，不能忽略已登记字段。保留跨仓库提交拓扑不同但内容一致的合法情形，不要求无关文档提交后机械重跑。

修复后验证：真实成功依赖必须带可核验文件；删除/改写日志、改写输入或产物、同 HEAD 不同源码指纹、仅自述 source HEAD、报告 hash 变化、failed/blocked/陈旧报告均不得通过；对应缺前置证据写完整 summary 并退出 2。正常依赖及明确无影响的文档提交应有正向测试。

### R03（P1，续 F03）：合法 system/workbook Issue 经模型默认序列化后被 Schema 拒绝

位置：`service/src/heater_drawing/domain/models.py:670-690` 的 Issue 第二个条件；已导出的 `schemas/revision.schema.json` 对应 `$defs.Issue.allOf`。

复现：构造合法 system Issue（`CAPABILITY_UNAVAILABLE`、skippable=false，不带行位置）；Issue 模型与原始输入的 Schema 均接受。执行 `Issue.model_validate(payload).model_dump(mode="json")` 后，模型正常补出 `row_id:null,sheet:null,excel_row:null`；Schema 仅因这些 key 存在，就触发“必须是非空 string/string/integer”，产生三条类型错误。workbook 相同；把这种合法 Issue 放入 `Revision.create()`，整个 Revision 的默认 JSON 也不能通过公开 revision Schema。

证据：`results.json: probes.issue_roundtrip` 保存原始输入是否通过、完整输出与 Schema 错误。

影响：C02 明确这些定位字段可为 null。新增“先结构、后语义”的强制消费规则会在第一层拒绝服务自身产生的合法系统/表级错误，属于 F03 修复引入的实质回归。

修复要求：条件应辨别“有非 null 行定位值”和“字段存在但全部为空”，使非 row Issue 可省略或显式 null；row Issue 仍必须有完整且非空定位，半套非 null 定位及冲突位置仍拒绝。不能只要求调用方一律 exclude_none 或删除 Python 的错误定位校验来掩盖 Schema 与契约矛盾。

修复后验证：对 system/workbook/row Issue，以及包含这些 Issue 的完整 Revision，分别执行默认 model_dump_json → Draft 2020-12 → 共享语义入口的往返；覆盖省略、全部 null、部分 null、完整位置、错位位置及非 row skip。Python/Schema/ECMAScript 结构消费按已写明的层次一致。

### R06（P1，续 F06）：Revision 实例的 hash 验证可绕过，冻结顺序也未闭合

位置：`service/src/heater_drawing/domain/models.py:369-382,488-489`。

复现 A：用公开 `Revision.create()` 建立合法三行 Revision，正常 hash 为 `fce4...8afe`。尽管顶层 frozen，`revision.final_scales` 仍是可变 dict；执行 `revision.final_scales["Sheet1:2"] = Scale(denominator="2",label="1:2")` 后，重算 hash 已为 `3760c7ae146f08ead426fe9a67c406d0e394d32ef387f032d03d8631bdb9525a`，但 `validate_revision_hash(revision)` 因 isinstance 直接返回，**接受旧 hash**。同一个对象 dump 成字典后交给该入口则拒绝。未使用 model_construct、object.__setattr__ 等绕过手段。

复现 B：在合法三行内容中只倒序 expected_row_ids，`Revision.create()` 接受，且 hash 与原序完全相同。当前只验证集合分区，未验证 R05 要求的“原顺序所有记录减跳过记录”；hash 投影未纳入 expected 列表，也没有建立它唯一可派生的顺序约束。

证据：`results.json: probes.revision_mutated_model/revision_mutated_mapping/revision_reordered_expected/revision_known_projection`。

影响：契约指定的验证入口不能保证它接收的实例仍绑定当前内容；同一 revision hash 还可携带不同的冻结页序。C01 的不可变修订和 R05/R06 的确定顺序不能据此交接。

修复要求：实例也必须验证当前内容/嵌套结构与 hash，或真正保证不可变嵌套结构；不能把 isinstance 当作已验证证明。expected_row_ids 应按 rows 原序减跳过集合派生并核对；如选择将其加入 hash，也仍要遵守原序规则。无需实现队列/出图服务。

修复后验证：创建后正常 dict/list 变更必须被禁止，或再次校验时拒绝；覆盖 final_scales、rows、skip 绑定等。模型实例与同内容 JSON/dict 的校验结果一致；倒序/错序 expected 行不能携带原 hash 成为合法 Revision，正确顺序和原有固定向量/34 项字段 mutation 测试继续通过。

### R07（P1，续 F07）：空边界采样/空基线仍可作为有效比较证据

位置：`scripts/verify_batch.py:318-360`、`scripts/check_source_boundary.py:288-300`。

复现 A：runner 边界文件只给 `schema_version=2,status=passed,mode=comparison,missing=[],errors=[],comparison={status:unchanged}`，加上当前真实 source fingerprint 和当前时间；没有 repositories、reference_files、baseline_sha256、真实 baseline 或任何采样明细。runner 仍返回 **0/passed**，source-boundary check 称 valid comparison。

复现 B：只在独立模拟参考根运行 `collect({"schema_version":2,"status":"passed"},...)`；这个 baseline 完全没有参考采样，collect 仍给 status=passed，把全部仓库/参考文件“从 null 到当前状态”作为 unknown_external 变化。记录到 baseline_sha256 只是给空对象算 hash，没有证明采样完整或比较双方对应。

证据：`empty-boundary.json`、`runner-cases/empty_boundary/summary.json`、`additional-results.json: boundary.empty_passed_baseline_*`。正常真实边界前后采样和同路径变化检测确实通过，不能据此认为无明细/缺 baseline 的输入也有效。

影响：C07 的边界门槛仍可在没有完成必要外部观察时通过，F07“证据结构、对应采样和缺失项验证”没有闭合。

修复要求：验证本批要求的仓库/参考文件覆盖、记录形状与必要 hash，核验比较结论与明细一致，并绑定可读取且完整的 baseline；拒绝空/截断/不对应的 baseline 和 comparison。保持只读，允许真实外部变化，归因不明仍应如实保留，不能回滚外部改动或以“外部项目必须不变”代替验证。

修复后验证：完整前后采样正向通过；空数组/缺数组/缺 baseline/错 baseline hash/错误源指纹/陈旧采样/伪 unchanged 结论/缺参考项均不得 passed。模拟首次变更、已脏同路径再变更、提交推进、未跟踪文件和引用变化仍能被观察，真实参考根只读采样复验。

## 5. 交接、剩余风险与停止点

本轮为 FAIL，B01 继续不具备后续 Batch 前置资格；progress 仅把 B01 更新为 failed 并链接当前审查，不改任何未来 Batch。旧 `docs/evidence/B01/summary.json` 已失效；`B01-fix/summary.json` 虽真实记录修复者自验 passed，也因本复审发现上述遗漏不能充当已获独立通过的前置证据。后续必须消费修复完成、版本对应且经独立复审认可的最新有效 summary。

B02 的模板/字体、真实 DXF/PDF/DWG 与 CAD 编辑和后续人工工程签收均未开展，未纳入本批通过声明。本批无人工门槛，缺人工探针只验证 runner 能阻断，没有生成任何虚假批准。

新增/更新范围仅为 `docs/reviews/B01.md`、初审归档 `docs/reviews/B01-initial.md`、`docs/evidence/B01-rereview/` 与 progress 的 B01 文档交接。新证据目录用 `* -text` 保留原始字节，原始日志及 .txt 副本入库；没有新增忽略规则、删除成果或改写业务文件。所有 venv、wheel、缓存和模拟仓库留在临时目录/既有环境，不入库。

两端完成文档提交后，确切 HEAD/分支/status/diff-check、与复审开始版本的改动范围及报告 hash 记录在 `docs/evidence/B01-rereview/git-handoff.json`；随后只提交该交接记录，并再次确认两端 porcelain 为空、diff-check 退出 0。最后一条交接记录提交不能自包含自己的 hash，最终 HEAD 以各库 `git log -1` 为准。调度 state 保持本轮开始字节。完成后停止，未进入 B02。
