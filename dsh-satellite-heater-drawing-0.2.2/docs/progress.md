## 0.2.1：基础聊天 UI 的 heater 按钮

仅修改 heater 客户端，保留 custom.agent 注册，新增 conversation.session.header.actions
按钮；真实 Chromium／React 的基础槽位测试宿主验证可见、当前会话新标签页、编码、
无会话禁用通过。包内 81 个运行文件与已验收 0.2.0 相同。未修改或安装真实宿主。
详情见 [按钮版本交付](header-button-021.md)。

# 2026-11-10：0.2.0 tgz 插件开发交付

用户本轮要求 5090 上的 tgz，明确接受不执行真实 DSH 安装测试。已实现独立后台、
profile/session 隔离、任务持久化、可信 Host 代理、受限对话工具与上传／出图／确认
工作台；最终 npm tgz 从全新 profile 解包离线启动，真实浏览器与原生 CAD 14 项
端到端检查通过，176 项回归、2 项原生决策集成和 5 项 Host 测试通过。
详见 [插件交付报告](plugin-release-20261110.md) 和
[最终包验收](evidence/plugin-release-20261110/summary.json)。
本次为精简实现的开发验收，未执行真实 DSH 安装、AutoCAD 复开或工程正式审批。
下方 Batch 表保留为原计划历史状态，不代表本次各模块尚无实现，也不将其全部门槛改成 passed。

# 矩形加热器插件进度

## 2026-11-09 原生 DWG/PDF 扩展

用户确认同时交付可编辑 DWG 与 PDF；业务值以 Excel 为准；首版沿用当前
模板结构，打印外观按工程师样例保留，不校正样例约 4.2% 的放大。
新增 `dwg_pdf_v1` 和 `scripts/generate_heaters.py`：Excel → 受控 DXF →
OpenCADStudio 严格保存 DWG2018 → 重开、反向 DXF 语义验证 → 按每张图框
打印 PDF → 合并、独立重打比对、原子发布。恢复样例 TXT 单线尺寸字体和
5mm 纸面字高；补齐私有运行字体；按样例统一 PDF 物理线宽。技术要求块
恢复样例原位置与八条原换行，使用实际 HZ 字形矢量边界检查可变文字越界。
尺寸线恢复样例文字上置与延伸线间距。修正原生 TXT 替代字体的页脚空格
宽度问题，页脚、阶段标记和更改单号字符保持可编辑，并增加最终 PDF 字形
位置回归检查。
原始 TXT 字体文件未提供，当前使用 CAD 内置替代，数字轮廓仍可能与
AutoCAD 样例不同；未宣称逐像素一致。

实现说明与运行命令见 [原生出图](native-dwg-pdf.md)。测试及实测记录见
[本次证据](evidence/native-dwg-pdf-20261109/summary.json)。这是 B05 出图与
交付引擎的扩展，不代表 B06 服务、B07 DSH 接入、B08 工作台或 B09 工程
人工验收已经完成；下表原有里程碑状态继续保留。

历史批次记录（本次原生扩展之前）：B02 开发技术独立审查已 PASS，正式加工审批仍 pending；当时 FreeCAD/AutoCAD/DWG 限制保留在对应报告中。B03 独立复审 PASS（F01-F05 全关闭）。B04 fix-3 独立复验 PASS，R01-R04 全关闭。B05 fix-1 独立复核已关闭原 R01-R04，但新增 B05-R05/P2；B05-fix-2 已完成公式单元格门禁修复与开发侧定向验收，指定 skip 集合仍为源行 `Sheet1:2`/`Sheet1:4`（跳过 Excel 第 3 行 `Sheet1:3`），当前等待独立复验，不宣称独立 PASS。

本文件属于 `heater-drawing`。同级喷漆与多层项目的 B01/B04 进度、ODA测试或许可不计入本表。

## Batch 状态

| Batch | 内容 | 依赖 | 状态 | 报告/下一步 |
|---|---|---|---|---|
| B01 | 项目/材料/契约 | 无 | passed | [独立复审 PASS](reviews/B01.md)；[获认可的最新 summary](evidence/B01-fix-2-r2/summary.json)；[第二轮修复报告](reports/B01.md)；不得以已 superseded 的 B01-fix-2 替代前置证据 |
| B02 | 模板/小样/DWG门槛 | B01 | passed | [本轮实现报告](reports/B02.md)；[独立开发技术审查 PASS](reviews/B02.md)；正式加工审批 pending，FreeCAD limited、AutoCAD unverified、产品 DWG 延期 |
| B03 | Excel校验 | B01 | passed | [实现报告](reports/B03.md)；[独立复审 PASS](reviews/B03.md)，F01-F05 全关闭；不得描述成可交付图纸 |
| B04 | 排版/DXF | B02,B03 | passed | [实施报告](reports/B04.md)；[独立复验 PASS](reviews/B04.md)，R01-R04 全关闭；仅限开发验收，不是加工批准 |
| B05 | PDF与交付包 | B04 | in_progress | [fix-2 实施报告](reports/B05.md)；[B05-fix-2 开发验收证据](evidence/B05-fix-2/summary.json) passed，等待独立复验；B06 尚未启动 |
| B06 | 服务/任务/恢复 | B05 | not_started | 等待可调用完整引擎 |
| B07 | DSH Host/MCP | B06 | not_started | 需核查真实Host版本/测试profile |
| B08 | 工作台 | B07 | not_started | 等待可信代理/确认路径 |
| B09 | 工程端到端验收 | B08 | not_started | 需实际CAD和命名工程审阅人 |
| B10 | 无Docker部署 | B09 | not_started | 需候选验收、环境配置与适用安装授权 |

状态枚举：`not_started / in_progress / blocked / failed / passed`。Batch未开始时未来门槛不是已经发生的blocked；执行后才能据实更新。passed须有报告与C07完整证据；不得把“已写文档”当实现通过。

## 已锁定决定

- 独立Linux服务＋DSH前端/Host，独立Python环境＋systemd，不用Docker，不依赖几何/热或旧CAD容器。
- Excel动态字段权威；固定模板/工艺；仅比例可通过用户确认覆盖，保留最终Excel和原输入。
- 任何错误先暂停，用户修改或明确确认跳过；冻结集合全部通过后才发布合并PDF/交付包。
- 2026-11-09 用户将交付范围更新为 DWG/PDF；新增原生正反向保存、语义回读及重打比对证据。原 DXF/PDF profile 保留兼容；目标 AutoCAD 与工程人工验收仍未执行。
- 保存位置为本独立目录，历史v0.6/v0.8/v0.9保留。

## 待实施时落实的人工门槛

| 事项 | 时点 | 状态 |
|---|---|---|
| 原生模板映射、黑黄线、HZ 字体、PDF 临时字体、尺寸再生成、样例引线与 fallback | 加工交付前 | 开发方向已确认；正式工程审批pending（当前开发基线使用统一引线规则） |
| 产品 DWG 范围/适用评估与生产许可 | B02/B10 | 用户已确认原生 DWG/PDF 开发范围；原生正反转检查已实现，目标 AutoCAD、正式生产审批仍 pending |
| 目标CAD环境与工程审阅人 | 交付前/B09 | FreeCAD宿主测试完成但兼容受限；AutoCAD未验证，待具名工程验收，不阻塞本轮开发 |
| 实际DSH测试profile/安装兼容 | B07 | pending |
| 部署账户/目录/端口/保留策略/安装窗口 | B10 | pending |

运行时逐批比例、跳过、人工复核不是一次性项目授权，必须绑定各次revision/run/产物hash。

## 更新规则

1. 开始某Batch：检查前置报告、代码状态、当前instructions，改in_progress。
2. 结束：写 `docs/reports/Bxx.md`、`docs/evidence/Bxx/summary.json`；表中链接真实存在报告，列命令结果和未决事项。
3. 修改影响旧门槛：标明失效范围和重验要求，不能沿用过期批准。
4. 不自行勾选人工通过，不复制另一个项目状态，不覆盖历史证据；新run新目录，summary指向最新有效检查。

## 本次计划检查

详见 [planning-validation.md](reference/planning-validation.md)。该检查仅覆盖文档结构、引用、Batch依赖、必要章节及材料清单，不表示计划中的业务验收命令已经执行。
