# B03 独立审查修复报告

状态：**F01-F05 已修复，当前源码 B01 与最终 B03 统一验收均 passed，等待同一独立审查人复审**。本轮没有进入 B04，也没有修改独立审查结论或原始审查证据。

日期：2026-11-09（Asia/Shanghai）

## 修复结果

### F01：XLSX Decimal 精度、下溢与溢出

- 新增统一的数值单元格可表示性检查。数值必须有限、不超过 Excel 15 位有效数字，并且经 openpyxl 实际序列化后可还原为相同 Decimal。
- `validate_rows` 在写文件前产生带行号、字段、原值和修复建议的 `INVALID_FIELD`；错误行仍保留在 `source_rows`，整批 `outputs=[]`。
- `write_actual_workbook` 在创建目标目录前完成同一预检。直接调用遇到不可表示值会抛出明确的 `UnsupportedExcelNumeric`，不会泄漏 `OverflowError` 或写半成品。
- 正常数值继续写为 XLSX numeric cell；真实案例实际工作簿重读后 17 字段逐项一致。

### F02：损坏 XLSX 逃逸异常

- ZIP/openpyxl 边界新增 `KeyError`、`zlib.error`、`EOFError` 等已知损坏输入异常处理，并保留既有 `BadZipFile`、XML、I/O 和 openpyxl 异常处理。
- 缺 `sharedStrings.xml`、缺 `workbook.xml.rels` 和损坏 DEFLATE 三个原审查输入均返回 exit 1、完整 JSON、不可跳过的 workbook `UNSUPPORTED_INPUT`，且 `outputs=[]`。

### F03：Excel 错误和日期类型事实

- `ImportedHeaterRow.cell_types` 保留 17 字段的 openpyxl 单元格类型；reader 不再在验证前把日期/时间转成 ISO 字符串。
- Excel `t=e`、`t=d` 及实际 date/time 对象均产生准确行级问题。普通文字 `#N/A` 和普通日期样式字符串仍有效，公式拒绝行为不变。

### F04：无效 limits 与比例长度

- `WorkbookLimits` 的计数、字节数和字符数只接受正整数；压缩比只接受正有限数；`max_text_characters` 不得超过公开模型上限 256。
- `requested_scale` 的模型与验证均执行 256 字符上限，且长度检查发生在正则和 Decimal 解析前。
- CLI 手动解析限制参数；`nan`、`inf`、小数行数和文字上限 300 均得到 system `INVALID_REQUEST` JSON，不再由 argparse 或 Pydantic 中断。实际工作簿意外写出失败也会保留完整诊断 JSON。

### F05：Windows 保留名与 Unicode 控制符

- 使用 `PureWindowsPath.is_reserved()` 识别大小写、扩展名及 `COM¹`、`LPT²`、`COM³` 等 Windows 保留名。
- 拒绝 Unicode category 为 `Cc` 的全部控制符，包括 U+0085；不自动改名。`HEATER-COM1`、`COM10`、`LPT0`、`HX.1` 等邻近安全正例继续有效。

## 修改范围

- 实现：`service/src/heater_drawing/domain/models.py`、`service/src/heater_drawing/excel/{reader,validation,actual_workbook,numeric}.py`
- CLI 与验收注册：`scripts/check_excel.py`、`scripts/acceptance_registry.json`
- 回归：`tests/excel/test_invalid.py`、`tests/excel/test_b03_review_regressions.py`
- 报告与新证据：`docs/reports/archive/B03-initial.md`、`docs/reports/B03.md`、`docs/evidence/B03-fix-1/`

未修改 `docs/reviews/B03.md`、既有 `docs/evidence/B03-review/`、`docs/orchestration/`、模板、CAD/PDF、绘图、前端或其他业务项目。旧报告已逐字节归档，原文件与归档 SHA-256 均为 `002c7d05fad08ef79419a7676356f97d673c689bb609b726cc57c087e4f78ff2`。

## 验证与证据

Linux 权威实现提交为 `2059b2790973269b3e8ccf3fe1a429df0390499a`；本地实现提交为 `c10dc0a29562d9b6f12ece078a4236d9bcf71894`。两端历史独立，不要求提交 ID 一致。

| 检查 | 结果 | 证据 |
|---|---:|---|
| Windows `pytest -q tests/excel tests/contracts tests/planning` | 191 passed；最终 Excel 单集 86 passed | 本轮终端实跑 |
| Linux 同一受影响回归 | 191 passed；最终 Excel 单集 86 passed | 本轮终端与 B03 runner |
| 原审查输入 F01-F05 独立修复核验 | 19/19 passed，原输入 hash 前后不变 | `docs/evidence/B03-fix-1/repair/results.json`，SHA-256 `1a679549287677bc6a8001f90ed3233981cacfea7f60f231c59f822a570aa449` |
| 当前源码 B01 runner | passed；4/4 命令、10/10 checks；dirty_files=[] | `docs/evidence/B03-fix-1/b01-runner/summary.json`，SHA-256 `1f5f5732ec2c4de91ffd3a2eb8ed8ce80f41743dbab17266fd62d18d06fb5743` |
| 最终 B03 runner | passed；3/3 命令、3/3 checks；dirty_files=[] | `docs/evidence/B03-fix-1/b03-runner/summary.json`，SHA-256 `8a12b4e271c49603d67ac88370c4b0154c32f4d73c98e07249faeecb2c88ff18` |
| B01 外部边界 | passed，comparison=unchanged | `b01-boundary-before.json` / `b01-boundary-after.json` |
| 真实案例 | valid，3 行，O3=郑玲，数量原文保留，实际工作簿数值往返一致 | `repair/real-case.json` 与 `repair/real-case-actual.xlsx` |

最终 runner 使用的源码指纹为 `735540e7999cb70ed9bf9cc752625c2d7781d7b2393677a9c4fec8e48d156e31`。当前 B01 绑定 SHA-256 为 `d9043214540dc4b25dbdf1f1fdb2a7d2128feeb48f9f028ce040b825dbdefe94`。历史唯一接受摘要 `docs/evidence/B01-fix-2-r2/summary.json` 保持未改，SHA-256 仍为 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。

## 失败尝试

- 第一次本地 Excel 回归为 52 passed / 1 failed：旧测试仍期待超出 XLSX 精度的 Decimal 有效。只更新了与 F01 冲突的旧断言，没有放宽产品规则。
- 第一次 Linux 文件落位命令被 PowerShell 提前展开远端变量，目标复制前退出；重试使用逐项绝对路径。
- 第一次 B01 摘要只读命令因嵌套引号产生 `IndentationError`，后接绑定命令未执行；改用 jq 核验通过后才生成绑定。

结构化记录见 `docs/evidence/B03-fix-1/attempts.json`。这些失败均无业务文件副作用，成功重试和最终证据均另行保留。

## 边界与后续

- 本轮只修复 B03 F01-F05。比例放置、推荐比例、缺字、文字溢出和图面碰撞仍属于 B04，未提前实现或验证。
- B04/B06 仍必须同时消费 parse 与 validation issues；任一 error 都不得绘图。`source_rows` 是完整输入事实，不能用规范行集合反推源条数。
- 后续若修改源码指纹范围，必须重新运行当前源码 B01 并更新依赖绑定，不能复用本轮指纹或历史接受事实。
