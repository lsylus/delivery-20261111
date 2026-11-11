# B09 实现与复验入口

隔离实施根 `/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings`，分支 `codex/thermal-drawings-b09`。不修改 9999 或旧业务服务。新功能仅 paint，blanket 业务未启动。

运行 `.venv/bin/python scripts/verify_development.py B09 --report-dir docs/evidence/B09`。入口运行登记测试、构建、前置核验、真实 STEP/UI、MCP、真实 DWG 和来源边界检查。所有技术检查通过后，若尚缺独立审查，`scope_tests_status=passed,status=blocked,full_acceptance=false`，exit 2；技术失败 exit 1。独立审查由调度器安排，此脚本不生成批准记录。

审查者可在 `docs/evidence/B09/independent-review.json` 登记：decision=approved、scope=B09-development、reviewer、code_revision（被审源码提交）、code_fingerprint（development.json 同值）及 evidence_refs 的 path/sha256。源码 fingerprint 必须相同；仅文档归档产生后续提交时允许被审提交为当前祖先。缺少、过期、篡改审查均不放行开发门槛。技术复验不是独立审查。

原 `.venv/bin/python scripts/verify_batch.py B09 --report-dir docs/evidence/B09` 不变，B04/B07 full summary 或人工最终证据不齐仍 blocked/exit 2。B05 原生执行端未验证、正式 DSH 身份缺口和 AutoCAD 实物验收不能在本批改 completed。

局部检查：pytest tests/integration/test_paint_workflow.py；pytest tests/integration/test_b09_commands.py tests/contracts/test_development_gate.py；npm run build --workspaces --if-present；npx tsc -p tsconfig.b07.json；python scripts/run_b09_browser.py；python scripts/check_b09_mcp.py。浏览器使用 npm pack 后解包的两插件，随机 loopback 端口和一次性账号，不连接 9999。画面与下载证据在 docs/evidence/B09。

真实 gearbox 候选：已有 original.step，只读上传副本，选择 exact FaceRef。最大平面曾超 B08 采样预算，诊断保留；开发者随后选择最小可计算平面，用材料内参考方框验证几何/版本闭环。不能认定这个小圆形平面是工程师认可的喷漆目标；工程真值和原喷漆 DWG 对应关系仍待人工确认。大平面/复杂曲面能力未在 B09 擅自扩展。

通过屏幕圈画取得的 mm 值有显示坐标量化误差，浏览器方框面积按 0.01 mm² 显示拾取容差检查；HTTP 精确坐标方框按 1e-6 mm² 算法容差检查。二者均不是制造公差。

转换器作为已有 worker 进程组的子进程运行，取消/超时/恢复统一清理包含 Xvfb/ODA 的组；B04 默认独立进程组调用保持。真实转换取消测试等待外部进程启动后取消并核验无活跃成员。

## B09 R1 会话一致性

工作台首次读取 `/context` 后必须核对 URL `session`（若提供）；不一致时在读取 binding/model 前终止。身份与工程只有完整加载并再次确认会话后才发布。初始化加载期间即启动身份监视，URL 变化、身份变化或身份无法验证时撤销当前请求上下文、清空 provider/identity/project/model/result/selection/pending/run/bundle 及成功提示，所有操作不可执行。

PaintSessionApi 在服务请求发出前及 JSON 结果返回后核验当前身份；界面采用结果还须通过 epoch 与 URL 检查。保存包引用、下载和聊天草稿等副作用另在提交前复核身份。已提交的后端任务仍按其原有授权及版本规则处理，但旧页面不得继续查询工程、显示旧成功提示或写入保存引用；重新打开工作台才能建立新会话。该规则属于 B09 隔离开发范围，不以 B07 正式身份映射缺口豁免。
