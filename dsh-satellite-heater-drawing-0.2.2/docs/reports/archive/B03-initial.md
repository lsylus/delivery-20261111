# B03 Excel 导入与整批校验实施报告

状态：**开发实现及统一验收 passed，等待独立审查**。本结论只覆盖 Excel 导入、资源限制、17 字段规范化、非图面整批校验和实际工作簿写出接口；不包含比例放置、缺字/文字溢出、CAD、PDF、前端、跳过确认或正式加工批准。

日期：2026-11-09（Asia/Shanghai）

## 实现结果

- 新增 `parse_workbook(path, limits)`。只接收真实 `.xlsx` 和指定 `Sheet1`，按表头映射读取；保留每个非空业务行的 `Sheet1:{原行号}`、17 项 `raw` 原值及源位置。格式空行和空 R 列不生成记录，其他非空工作表只提示未处理。
- 新增 `validate_rows(rows, template=None, limits=None)`。实现 17 项必填、文字类型/长度、有限 ASCII Decimal、宽不大于长、阻值偏差范围、短/长边、`1:n` 且 `n>=1`、跨平台安全代号和 Unicode casefold 批内重复检查。重复代号对所有相关行各产生 `DUPLICATE_CODE`，不保留第一条后静默删除其余行。
- 沿用 `HeaterRow`、`RawHeaterFields` 和 `Issue`；新增 `ImportedHeaterRow` 表达尚未通过字段校验但必须保留的源行。Issue 只增加可选 `raw_value`，既有字段及 ErrorCode v1 未改名。CLI 的 `source_rows` 始终包含全部源记录，`rows` 是可构造的规范行；消费端必须合并 parse/validation issues 并在任一 error 时停止，不能只看 `rows` 是否非空。
- 公式以单元格类型识别，始终 `data_only=False`；不执行公式、不采用缓存值。普通文字即使以 `=`、`+`、`-`、`@` 开头仍可保留，实际工作簿写出时所有文字强制为字符串，数值使用规范值，数量、签署文字和比例等采用用户原文。
- XLSX 在 openpyxl 之前检查扩展名、ZIP 完整性/重复条目/路径穿越/加密/压缩方法、条目数、声明与实际解压总量、单条目压缩比、宏和外部关系。默认限制为 10 MiB、500 非空业务行、每表 501 个非空行、64 个非空列、2000 ZIP entries、100 MiB 解压总量、1000:1 压缩比、每个文字字段 256 Unicode 字符；均可配置。
- `scripts/check_excel.py` 对有效输入 exit 0、对任一 workbook/row error exit 1，并始终写完整 JSON。无效输入不生成 CAD/PDF；`--actual-output` 仅在无 error 时可写实际 Excel。

真实案例结果：仅 `Sheet1` 第 2/3/4 行；17 个规范字段逐项等于 `fixtures/case/expected.json`；O3 为“郑玲”；数量依次为 `18片`、`12（备份2）`、`76片（备份13片）`。原 XLSX SHA-256 保持 `25e06f4ce14b366fe6f4ca89af7ccda1f707af62a6aded16a87be7028417e4e5`。

## 修改文件

- 领域与 Excel：`service/src/heater_drawing/domain/{models,errors}.py`，`service/src/heater_drawing/excel/{__init__,headers,reader,validation,actual_workbook}.py`
- CLI/验收：`scripts/{check_excel,build_b03_fixtures,bind_b01_dependency,verify_batch,check_wheel_install}.py`、`scripts/acceptance_registry.json`
- 契约/说明：`docs/contracts.md`、`schemas/revision.schema.json`、`README.md`、`.gitignore`
- 夹具/测试：`fixtures/invalid/*.xlsx`、`tests/excel/*`、`tests/planning/test_runner.py`
- 新证据：`docs/evidence/B03/`；本报告和 `docs/progress.md`

没有修改 `docs/orchestration/`、模板、绘图、DXF/PDF、FreeCAD、前端或其他业务项目。

## 实际检查与证据

Linux 权威实现提交为 `7a57ae4364b556cf213b38e1df42cc3d70cb067c`，本地对应实现提交为 `e4b9ecb`。两端独立 Git 历史，提交 ID 不要求相同。当前源码内容指纹为 `3acb3a00dc6c50255b680ee0517987cb7f3af32f2c688aeeec8caf304a26ebce`。

| 检查 | 主机 | 退出码 / 结果 | 证据 |
|---|---|---:|---|
| `.venv/Scripts/python.exe -m pytest -q tests/excel tests/contracts tests/planning` | Windows | 0，158 passed | 本轮终端实跑；未把它冒充 runner 日志 |
| `.venv/bin/python -m pytest -q tests/excel tests/contracts tests/planning` | Linux | 0，158 passed | 本轮终端实跑；统一 runner 下方分拆留存同源码日志 |
| `.tools/uv build --wheel --project service --out-dir dist` | Linux | 0 | wheel 构建成功；隔离安装见 B01 runner |
| `verify_batch.py B01 --report-dir docs/evidence/B03/b01-runner` | Linux | 0，passed；53 contract、52 planning、Node、隔离 wheel 及 10 项检查通过 | `docs/evidence/B03/b01-runner/summary.json` 和同目录日志 |
| `verify_batch.py B03 --report-dir docs/evidence/B03` | Linux | 0，passed；3/3 必需命令、3/3 checks | `docs/evidence/B03/summary.json`，SHA-256 `8c96e3fa7ef47bb141a77c1023abea3460596452accbe1cd9e4fa9095a2c8731` |
| `check_excel.py` 真实案例 | Linux runner | 0，valid，3 行，outputs=[] | `docs/evidence/B03/case.json`，SHA-256 `25e9351827151a3fc37c527526da651d4ab91f03d0b5c51f271138f213ad20e3` |
| `check_excel.py` 综合无效夹具 | Linux runner | 1（预期），invalid；2 个源行均保留，第 3 行 6 个定位错误 | `docs/evidence/B03/invalid.json`，SHA-256 `d8dd866f5d2f202053941d5ebf5508c886565130a406759b482b817dcd546300` |
| `check_excel.py` 重复代号 / 公式夹具 | Linux | 各 1（预期）；重复行 2/3 均报错；公式原文保留 | `invalid-duplicate.json`、`invalid-formula.json` |
| Schema 导出后 contract tests | 两端 | 0 | `schemas/revision.schema.json` 与模型快照一致 |

B01 当前源码绑定为 `docs/evidence/B03/b01-acceptance.json`，SHA-256 `9a1bc5d144e690c344c2e43208c559e68453d1eae49aee423dc5233bc49d55e1`；它绑定本轮 B01 summary SHA-256 `62fe4eba71f7d9f493b5bcea75916ffe9c1884944c7d090c2278a8bd593f8bdb`，同时保留唯一历史接受事实 `B01-fix-2-r2/summary.json` SHA-256 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。B01 boundary comparison 为 unchanged。

未反复运行未受影响的 B02 FreeCAD、格式失败矩阵或 247 项全项目回归。`docs/evidence/B03/` 不含 DXF、DWG 或 PDF。

## 失败尝试（保留，不覆盖）

- 首次本地 Excel 测试为 46 passed / 2 failed：一项测试错误地用 `NaN == NaN`，另一项测试夹具被 openpyxl 自动写成真实公式而非公式式文字。只修正测试断言和夹具单元格类型后通过；没有放宽产品公式拒绝逻辑。
- 第一次远端 `git apply --check` 因两端独立历史中的 `docs/contracts.md` 和 registry 基线不同而退出 1，未应用任何文件。随后主体补丁与两份文档分别按远端原文件合入，未整文件覆盖本地调度原件。
- 一次只读 summary 检查因 SSH 引号错误退出 1；未修改文件。随后直接取回真实 JSON 核验并完成绑定。

## 尚未解决的问题

- 比例是否能放入图框、推荐比例、缺字、字形边界、文字溢出和碰撞仍属 B04；本批只校验比例语法及范围。
- 实际 Excel 写出函数已完成并有 roundtrip/公式注入测试，但交付集合筛选、修订绑定和最终 Excel 发布由 B05/B06 集成。
- 跳过确认、修订冻结、任务恢复、CAD/PDF、DSH Host 和前端均未实现。公式、宏、外链和合并业务单元格按首版契约明确不支持，不是待静默兼容项。
- B02 开发技术独立审查已 PASS；正式具名工程加工审批仍 pending，FreeCAD DXF 往返受限、AutoCAD 未验证、产品 DWG 延期。这些不阻塞本批 Excel 结果，也未被本报告扩大为已批准。

## 后续 Batch 必须知道的接口和约束

1. B04/B06 必须同时消费 `ParsedWorkbook.issues` 与 `ValidationResult.issues`。只要有 error 就不得绘图；`ValidationResult.rows` 中可能仍有重复代号等“字段本身可规范化但整批不合法”的行。
2. `source_rows` 是完整输入记录事实，`rows` 是规范行，不得用后者反推原条数。错误行、公式行和部分填写行不能被 dataframe 转换或 `dropna` 替代。
3. `raw` 保留 Excel 值；`values` 中 Decimal 和比例是 ASCII 规范字符串。数量不解析、不加减；签署文字不得用 0 或空值代替。实际工作簿写出必须继续强制文字单元格类型。
4. `template` 参数为 B04 预留，本批没有执行任何图面判断。B04 添加图面 Issue 时必须复用 `Issue`/ErrorCode，不另造错误结构。
5. 后续依赖若修改 `scripts`、`service/src`、`schemas`、`tests` 等源码指纹范围，必须重新生成当前源码 B01 绑定；不能只因文档 HEAD 变化机械判失效，也不能继续使用本轮指纹冒充新源码验证。

完成本报告与进度提交后只做两端 HEAD、`status --porcelain`、`diff --check` 和进程清理核对；最终提交 ID 在聊天交接中给出，避免报告递归引用自身提交。
