# 实施契约 v1

B02阶段约束更新（2026-11-09，适用于C05–C07）：开发验收执行 `check_format_gate.py --stage development`；默认/交付仍为 `--stage delivery`，严格保留原具名审批及AutoCAD证据门槛。开发检查要求精确候选DXF/PDF通过、实际引线边界矩阵通过、5090 FreeCAD 0.19.2实测证据完整且限制如实登记、DWG延期决定有效；已知FreeCAD兼容失败不能标成兼容通过，但不等于本轮技术调查未完成。开发passed不授予加工交付批准；后批在B02独立技术验收通过且满足依赖后，可由调度按最新用户授权继续。当前执行者仅完成B02。
本文件为 B01 开始实现的接口基线；B01 将其固化为 schemas 和 OpenAPI。未实现字段不可对外宣称可用。破坏性变更先改本文、schema_version、消费端和回归，不能两个 Batch 各自猜接口。字段采用 snake_case；枚举不以 UI 中文作存储键。

## C01：身份、修订和持久化

- `owner_id`、`session_id` 来自经过 DSH 认证的 Host，禁止采用浏览器/MCP 参数自报身份。Host 使用服务令牌和受信任身份头 `X-Heater-Owner`、`X-Heater-Session` 访问内网后端；服务仅接受配置的可信 Host。两头各做权限检查，令牌不写日志或插件包。
- ID 使用服务端 UUID；`row_id` 是 `{sheet}:{excel_row}`，其唯一性限定于 `revision_id`；`job_id` 一次导入，重传产生新 job 并可带 `replaces_job_id`，不原地覆盖原输入。
- `revision_id` 不可变输入/决策快照；每次接受比例、确认跳过、变更模板均创建新修订。`revision_hash` 为规范 JSON SHA-256，覆盖输入 hash、17字段原值/规范值、模板和字体清单 hash、最终比例、跳过行与原因、格式 profile。确认关联父修订和已展示的具体问题版本，不能复用到不同输入。
- `run_id` 每次运行新建，绑定精确 revision；重试也新 run。SQLite 事务冻结 expected_row_ids、claim worker lease、发布 artifact；过期/取消/旧 revision 的结果不得发布。
- 任务状态与行状态独立，行报告覆盖所有输入行，包括跳过行；正文/日志不得混入别的会话文件路径或令牌。

## C02：核心结构

```text
HeaterRow {
  schema_version: 1, row_id, source: {sheet, excel_row},
  raw: {17个字段原始值}, values: {requirements.md定义的17个规范字段}
}
Scale {numerator: 1, denominator: decimal-string, label: "1:2"}
Issue {
  issue_id, row_id|null, sheet|null, excel_row|null, code|null, field|null,
  raw_value|null,
  error_code, severity: error|warning, message, suggested_fix,
  scope: workbook|row|system, skippable: boolean
}
ScaleProposal {
  proposal_id, row_id, original: Scale, proposed: Scale,
  reason, measured_bounds_paper_mm, available_bounds_paper_mm,
  revision_hash, template_hash
}
Decision {
  decision_id, actor_id, decided_at, kind: scale|skip,
  base_revision_hash, issue_ids: [], proposal_ids: [],
  row_ids: [], reason, confirmation_receipt_id
}
Revision {
  revision_id, revision_hash, parent_revision_id|null, source_sha256,
  template_version, template_hash, font_manifest_hash, output_profile,
  rows: HeaterRow[], final_scales: {row_id: Scale},
  issues: Issue[], proposals: ScaleProposal[], decisions: Decision[],
  skipped_row_ids: [], expected_row_ids: []
}
DrawingPage {
  schema_version: 1, row_id, code, revision_hash, template_hash,
  scale: Scale, geometry_mm: {rectangle, lead_segments, dimension_definitions},
  fields: {17个动态字段}, fixed_text_version,
  placement: {model_origin_mm, tile_bounds_mm, paper_bounds_mm, layout_name},
  checks: {bounds, collisions, glyph_coverage}
}
Run {
  run_id, revision_id, revision_hash, state, expected_row_ids,
  row_results: [{row_id, state, issues, staged_artifacts}],
  started_at, finished_at|null, worker_lease, generation_token
}
Artifact {
  artifact_id, run_id, revision_hash, relative_path, media_type,
  bytes, sha256, row_ids: [], page_count|null,
  kind: dxf|dwg|pdf_single|pdf_merged|excel_original|excel_actual|report|manifest|zip
}
Review {
  review_id, actor_id, decided_at, status: approved|rejected,
  run_id, manifest_sha256, artifact_hashes, comment
}
```

Pydantic 禁止未知请求字段；JSON Schema 禁止任意执行代码、文件路径和上传模板字段。geometry 坐标单位始终 mm；Decimal 在 JSON 为十进制字符串，前端只作显示/选择，不重算工程几何。DrawingPage 为布局后的领域结果，DXF 与 PDF 不各自解释 Excel。原生 DXF 尺寸回读与 PDF 视觉均须单独验收。

### C02.1：结构校验与共享语义校验

- 十进制及比例仅使用 ASCII `0-9`，禁止 Unicode 数字、指数、前导零、首尾换行、NaN/Inf 和布尔代替整数。普通正尺寸允许 `0.001` 等小数；比例分母必须 `>=1`；仅 `Point`/`Bounds` 坐标允许前置 ASCII 负号，以便结构化表达超出纸面原点的诊断候选。
- JSON Schema Draft 2020-12 负责类型、enum、条件必填、非 row 不可 skip 和安全相对路径等结构约束。`row_id == "{sheet}:{excel_row}"`、`Scale.label == "1:{denominator}"`、revision 集合及 hash 等跨字段关系不能只靠标准 Schema 表达。
- `Issue` 的 `row_id/sheet/excel_row` 对 workbook/system scope 可省略或在默认 JSON 序列化中全部为 null；任一位置为非 null 时三项必须完整，row scope 三项必须为非空有效值。不得要求消费者使用 `exclude_none` 才能通过公开 Schema。
- 所有消费端必须先执行 Draft 2020-12 结构校验，再调用 Schema 的 `x-semantic-validator` 所指 `heater_drawing.domain.models.validate_contract_semantics`；不能只因 JSON Schema 通过就接受业务 payload。Python 模型本身执行同一语义入口。

### C02.2：错误编码 v1

`ErrorCode` 的初始固定集合为：`INVALID_REQUEST`、`AUTHENTICATION_REQUIRED`、`ACCESS_DENIED`、`NOT_FOUND`、`REVISION_CONFLICT`、`PAYLOAD_TOO_LARGE`、`UNSUPPORTED_INPUT`、`CAPABILITY_UNAVAILABLE`、`INVALID_FIELD`、`MISSING_FIELD`、`DUPLICATE_CODE`、`WORKER_INTERRUPTED`、`INTERNAL_ERROR`。Issue 与 HTTP error 共用该集合，未知值、拼写或大小写不同均拒绝。

新增编码必须在同一变更中更新本文、Python enum、JSON Schema、OpenAPI 和跨层测试；删除或改名属于破坏性变更，必须提升 schema_version。后续 Batch 不得绕过 enum 自造字符串。

### C02.3：revision hash 规范载荷

`revision_hash` 的规范载荷版本为 1，只包含且必须包含：`source_sha256`、按输入顺序的完整 `rows`（每行 raw 与 17 个规范 values）、`template_version`、`template_hash`、`font_manifest_hash`、`output_profile`、全部 `final_scales`，以及每个跳过行绑定的 `row_id/decision_id/issue_ids/reason/confirmation_receipt_id`。自身 `revision_hash`、`revision_id`、`parent_revision_id`、非 skip 决策、运行状态和时间不参与该内容 hash。

UUID 与 datetime 先由 Pydantic JSON mode 转为标准字符串；随后采用 UTF-8、键排序、紧凑分隔符、`ensure_ascii=false`、禁止 NaN/Inf 的规范 JSON，计算 SHA-256。`Revision.create` 是创建入口，`validate_revision_hash` 是验证入口；直接携带任意 64 位字符串不能构成有效 Revision。

`expected_row_ids` 必须严格等于 `rows` 原输入顺序中删除 `skipped_row_ids` 后的序列，不能只核对集合分区。`validate_revision_hash` 对 Mapping 和已构造 Revision 实例都重新校验当前嵌套内容及 hash；顶层 frozen 不能被当作嵌套 dict/list 从未变化的证明。

## C03：状态机与确认规则

```text
uploaded -> validating -> awaiting_resolution | ready
awaiting_resolution --有效决策生成新revision并重新校验--> awaiting_resolution | ready
ready --start(冻结集合)--> queued -> running -> generated
running --行绘制/回读/渲染错误--> paused_error
running --系统错误--> failed
queued/running --cancel--> cancelled
paused_error --retry(相同revision，新run)--> queued
paused_error --明确skip(新revision，全量重新校验)--> awaiting_resolution | ready
generated + review=pending --人工审阅--> review=approved | rejected
```

校验错误或未决比例不进入 queued。初始建议全部 valid 且无需比例变更时可点击生成，无额外“同意输入”弹窗。跳过仅用于指定 row 的 skippable issue；同代号冲突的所有相关行均列错误，确认跳过其中行后重验唯一性，其余可恢复有效。workbook/system issue 不可跳过。

确认 receipt 由 Host 在用户真实确认事件后生成，一次性、绑定 actor/session/action/revision/具体 issue/proposal 集合。服务核验 receipt 消费；刷新/竞态必须 409 并重取状态。对话工具若无宿主可靠确认机制，首版只提供读状态、解释问题及打开确认页面；AI 不得用普通 `confirmed:true` 伪装人类操作。

发生新运行错误后之前 skip receipt 无效于该新 issue。用户跳过后新 revision 必须重新核验比例与全集，再从头生成，首版不跨 run 复用部分成品；这降低混合版本风险。只允许一个活动 run/revision；SQLite 单 worker 原子 claim。进程意外重启将失联 run 标记 `paused_error`、issue `WORKER_INTERRUPTED`，显示可重试而不自动发布。

`generated` 表示全部预期产物技术通过并原子发布到送审集合，review 仍为 pending。UI/下载页醒目标“待工程复核”。人工 approved 后才允许“已复核交付”标识。不用签名图片冒充审核。后续修改生成新 run，不能继承旧审核。

## C04：HTTP API

服务前缀 `/api/heater/v1`；错误结构 `{error:{code,message,details,request_id,current_revision_hash?}}`。400 格式错误；401/403 身份；404 不存在/不可见；409 修订或状态冲突；413 超限；422 不支持的输入结构；503 能力/队列暂不可用。业务逐行校验结果通过 job 状态返回，不把可诊断行错误都变成 HTTP 500。

| 方法/路径 | 请求和结果 | 归属 |
|---|---|---|
| GET `/healthz`、`/readyz`（无前缀） | liveness / schema、DB、模板/字体就绪；不输出秘密路径 | B06 |
| GET `/capabilities` | schema版本、限制、模板版本、格式可用性和限制、worker状态；DWG未启用明确false | B06 |
| POST `/jobs` | multipart file、safe output_name、可选replaces_job_id；202 job/revision/status | B06 |
| GET `/jobs/{id}` | job、当前revision、issues、proposals、counts、run、review状态 | B06 |
| POST `/jobs/{id}/decisions` | base_revision_hash、scale proposal_ids、skip issue_ids/row_ids、reason、receipt；返回新revision | B06/07 |
| POST `/jobs/{id}/runs` | revision_hash、Idempotency-Key；202 run，重复同键同payload返回原run | B06 |
| GET `/jobs/{id}/runs/{run}` | 逐行状态、总体进度、失败原因 | B06 |
| POST `/jobs/{id}/runs/{run}/cancel` | revision_hash；终止排队/执行，不发布部分包 | B06 |
| POST `/jobs/{id}/runs/{run}/retry` | revision_hash、新Idempotency-Key；仅允许可重试状态 | B06 |
| GET `/jobs/{id}/runs/{run}/artifacts` | 仅列完整published送审集合；失败时仅诊断信息 | B06 |
| GET `/artifacts/{artifact_id}/content` | owner/session检查；PDF预览或附件下载；禁止传入本地path | B06 |
| POST `/jobs/{id}/runs/{run}/reviews` | manifest hash、approved/rejected、comment、人工receipt | B06/07 |

范围统一：所有业务 API 都执行 owner/session 校验；job 归属不由 payload 决定。上传和决定有输入大小限制；下载不接受任意 URL，不做代理 SSRF。服务令牌只支持受控 Host 入口，监听回环或经防火墙批准的内网地址，不假定所有 DSH Host 与服务同机。B07 实测拓扑后定配置。

## C05：出图引擎接口与发布

```text
parse_workbook(path, limits) -> rows + workbook/row issues
validate_rows(rows, template) -> issues
plan_pages(revision, template) -> DrawingPage[] + issues + scale proposals
export_dxf(pages, template, output_path) -> candidate + readback report
render_pdf(dxf_path, page, render_profile, output_path) -> candidate + page report
build_delivery(revision, run, candidates, output_dir) -> manifest candidate
validate_delivery(expected_row_ids, manifest, files) -> pass/fail
publish_delivery(run, generation_token, verified_candidate) -> artifacts
```

`plan_pages` 不调用 AI，结果固定输入确定；实际 bytes 可能含工具时间戳，验收比较语义和记录每次 hash，不承诺未归一化字节总相同。PDF 以生成的 DXF 和相同 page 裁切配置渲染，避免另写一套几何。汇总 PDF 使用已通过的单页按行序合并，合并后页序/渲染与各原页对应。

候选文件只在独立 staging；验证通过且事务确认 run 仍有效，再在同文件系统原子 rename 整个目录并登记。崩溃在 rename/DB 之间需恢复扫描，只有 DB 已发布且 hash 匹配的目录可下载；孤儿目录不公开。系统异常不得发布“已生成的前几张”。输出编码/路径以 `manifest` 为准，禁软链接逃逸、路径遍历、覆盖历史产物。

输出模板版本和字体 hash 是复核输入；PDF 与 DXF 字段值、数量原文、比例、行集合一致。最终 Excel 不增加虚构业务参数；变更记录单独 sheet。系统生成 Excel 时把文本强制为文字单元格，防止以 `=` 等开头的输入在导出时被解释为公式。

## C06：DWG adapter（默认 disabled）

接口 `capabilities() -> capability record`、`convert(dxf, target, profile, timeout) -> candidate + evidence`。必须是固定可执行程序＋参数数组，不使用 shell 拼接用户输入。每次转换独立目录、日志、超时和进程组清理；检查 exit code、文件头/大小，再 DWG→DXF 回读检查单位、图元类型、坐标、图层、中文、原生尺寸。转换回读不替代目标 CAD 编辑验收。

capability 区分 `not_configured / available_unverified / verified_evaluation_only / production_ready / failed`；记录实际版本、文件 hash、字体、license_scope、真实运行证据、目标 CAD 编辑证据。文档或文件存在不能返回 production_ready。未开启时 DXF/PDF 不得以 ODA 为运行依赖；已明确开启首版 DWG 时其失败阻止该集合发布，不能悄悄降级。

本插件几何没有孔、保护阴影、折线搭接或固定点。其他项目的这些小样可作工具覆盖参考，**不是本插件新业务需求**。本项目必须验证矩形、双引线、17字段、固定文本、黄色图框、两个比例和原生标注。

## C07：通用 Batch 验收与证据

B01 创建 `scripts/verify_batch.py` 和 `scripts/acceptance_registry.json`。统一执行：

```bash
.venv/bin/python scripts/verify_batch.py Bxx --report-dir docs/evidence/Bxx
```

runner 依 registry 按 argv 调用明确测试/探针，不接受任意 shell；保存每个 command 的 argv、cwd、真实退出码和日志。exit 0=全部必需项通过且人工门槛满足；exit 1=技术失败；exit 2=缺环境/人工证据/前置门槛；不可用或 skip 不能计 pass。每个 Batch 新增测试与注册项，不能预先给未实现 Batch 空列表通过。必需测试被跳过、零测试收集、找不到文件一律不能 pass。

`summary.json` 至少包含 batch、status（passed/failed/blocked）、source_git_head、dirty_files、contract_version、dependency_reports及其hash、commands、checks、input_hashes、artifact_hashes、human_decisions、blockers、timestamp。人工证据必须有姓名/时间/范围/确切文件 hash/结论；不得自动生成虚假批准。

前置验收源代码有变更时比较影响范围并重跑必要检查；记录结果，禁止仅凭 report 存在放行。测试、真实转换、工程复核分别列出。报告保存可再现命令及偏差；业务源代码和本次文档写入状态分开报告。

前置报告登记同时绑定 report hash、source Git 版本、`source_contract_sha256`、契约版本和最大时效。runner 必须逐个核验报告引用的必需命令日志、输入 hash 和产物 hash 对应的项目内文件；缺失、改写、空证据或源码内容指纹不符均为 blocked/exit 2。只改不在源码内容指纹范围内的交付文档时可保持前置有效，但必须继续匹配已登记的报告版本和内容指纹，不能仅凭当前 HEAD 名义相同放行。

source boundary comparison 必须登记并读取完整 baseline，核对 baseline 实际稳定 hash、源码指纹、时效、固定仓库和参考文件覆盖、tracked/untracked 内容 hash，以及由前后快照重新计算的 comparison 结论。真实外部变化允许为 `changes_observed/unknown_external`，但空、截断、伪 unchanged 或不对应 baseline 的证据不得通过，也不得写入或回滚外部项目。
