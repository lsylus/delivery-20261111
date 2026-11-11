# 本次计划检查记录

日期：2026-11-07。范围仅为开发计划；未运行计划中的业务测试、CAD转换、插件构建或部署命令。

## 结构检查

机器结果保存在 [plan-check.json](plan-check.json)：检查10个Batch编号连续，每批包含用户要求的6项及交接章节；所有本地Markdown文件链接存在；Batch依赖无环且与plan/progress表一致；10个案例原件hash可核对。该JSON不是C07业务验收报告。

## 需求覆盖

| 需求/风险 | 主责Batch | 复验 |
|---|---|---|
| 独立项目、不动旧业务、历史文档保留 | B01 | B07/B10边界 |
| 17字段、Excel权威、原行号、数量文字 | B03 | B05/B09 |
| 固定模板/黄色框/字体/技术要求 | B02 | B04/B09 |
| 真1:1几何、可编辑标注、1:2纸面 | B02/B04 | B09目标CAD |
| 比例推荐须确认、最终Excel留痕 | B04/B06 | B08/B09 |
| 错误先暂停、明确skip、无静默漏页 | B05/B06 | B08/B09 |
| DWG尽早真实验证、许可与编辑限制 | B02 | 启用后B09/B10 |
| UI/Host/微服务分离、身份与会话 | B06/B07 | B08/B09 |
| 重启/取消/迟到结果/并发确认 | B06 | B09/B10 |
| 原输入/最终表格/报告/清单/hash | B05 | B06/B09 |
| 人工复核与生成完成分开 | B06/B08 | B09 |
| 无Docker、独立venv、systemd | B10 | 部署smoke/回滚 |

## 脚本责任核对

下列脚本是未来实现任务，本次均未创建业务实现。每个Batch必须创建自己验收需要的入口并接入统一registry，不能以“脚本不存在”为由把项目标为通过。

| 入口 | 创建/维护Batch |
|---|---|
| verify_batch.py、acceptance_registry.json、check_source_boundary.py | B01建立；每批补注册/证据 |
| probe_formats.py、check_format_gate.py | B02 |
| check_excel.py | B03 |
| draw_case.py、check_drawing.py | B04 |
| build_delivery.py、check_delivery.py | B05 |
| smoke_service.py | B06 |
| check_plugin_package.mjs | B07 |
| playwright.config.ts与workspace.spec.ts | B08 |
| acceptance_engineering.py | B09 |
| preflight.py、install_release.py、backup_restore.py、smoke_deployed.py | B10 |

## 内容审阅结果与限制

- 将现有ODA证据更新为“另一项目已跑真实转换、仅评估、AutoCAD重开未做”，没有使用旧的“未安装”绝对结论，也没有扩大成生产可用。
- 将DXF/PDF基线与DWG有条件扩展分开，B02必须留决定；首版若升级DWG，要相应提高B04/B09/B10门槛。
- 模板坐标/字体/引线参数未测量的事实明确交给B02；未编造定量数据。
- 每批列出未来新增路径、API/数据结构、失败条件和真实工具/人工门槛；新聊天入口在plan §6。
- 所有开发状态保持not_started。源目录只新增本独立docs文档；原业务代码、同级另一项目docs及历史版本未修改。

尚无业务代码，因此这次检查不能证明最终排版、性能、CAD兼容或平台安装可行；这些都有明确负责Batch和可执行门槛。
