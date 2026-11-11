# 独立验收任务模板

审查 Batch Bxx，不修改业务代码。

先阅读项目适用 AGENTS.md、docs/plan.md、docs/progress.md、docs/contracts.md、docs/batches/Bxx.md、必要前置 Batch 交付与独立审查报告，以及本批 docs/reports/Bxx.md。

依据任务说明检查实际实现与验收结果，不要仅依赖执行者的交付报告。必须读取代码、检查实际改动、运行必要验证，检查依赖及证据的时效、来源与对应版本。不接受其他插件结果、mock、只有 HTTP 200、截图或测试数量作为真实外部能力及人工门槛通过的替代。

输出 docs/reviews/Bxx.md：
- PASS 或 FAIL
- 检查依据和验证结果，实际命令、退出码、版本及证据位置
- 必须修复的问题：具体路径/位置、触发条件、验收影响和修复后验证要求
- 剩余风险

存在影响验收的问题时必须判定为 FAIL。缺关键外部环境或人工确认时不得判 PASS；列明真正阻塞与执行者还能完成的独立工作。不能自行扩大范围、弱化验收或代替用户作工程签收。

审查可写本批独立审查报告和独立验收证据，不修改业务代码、既有测试或执行报告；避免覆盖执行者证据。发现问题交给调度器发回原执行聊天。没有调度器新指令时不进入其他 Batch。

用户要求保持 Git 干净。核对本地与远端仓库 HEAD、分支、`git status --porcelain` 和 `git diff --check`。在执行者停手后提交本批审查文档/允许入库的证据，不提交密钥、运行环境或临时产物，不修改业务代码。报告记录交接状态。不得为取得 clean 删除成果、忽略业务源码或回滚外部改动。

远端开发根为 5090-qmh:/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing，先核对身份与报告中的实际位置。本地调度根为 C:\Users\HUAWEI\Documents\ChatGPT\矩形加热器插件\heater-drawing。审查结论必须同步到本地调度根 docs/reviews/Bxx.md；证据路径写清。不要改写 docs/orchestration/state.json。

最终回复只给 PASS/FAIL、简短结论和报告路径。调度器不读业务代码，必须在审查报告里写明可执行的修复要求和关键事实。
