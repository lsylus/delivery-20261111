# 项目与环境核查

核查日期：2026-11-07（Asia/Shanghai）。范围：读取本地原始材料的已提取证据、历史加热器计划、5090 Git 状态与指定源文件、既有转换能力报告。未安装、转换、测试业务或部署。

## 1. 当前目录和资料

- 本地计划目录：`C:\Users\HUAWEI\Documents\ChatGPT\插件\heater-drawing\docs`，经用户明确选定。
- 同级 `C:\Users\HUAWEI\Documents\ChatGPT\插件\docs` 属于喷漆与多层插件，已有 B01/B04 实施资料；不得覆盖或当成此项目的完成记录。
- 原包：`D:\小卫星\插件\矩形加热器自动出图案例.zip`。
- 已解压副本：`C:\Users\HUAWEI\Documents\ChatGPT\插件\work\heater_case\矩形加热器自动出图案例`。
- 核查资料：同工作区 `work/heater-case-audit.md`、`heater-excel-values.json`、`heater-docx-text.txt`、`heater-pdf-annotations.txt`，以及 `work/heater_case/renders/` 与 `media/`。需求必需内容已收录 [requirements.md](requirements.md)，不依赖聊天。
- 原材料 10 个文件：`CAD模板.dwg`、`加热器图纸.dwg`、`加热器图纸.bak`、`加热器图纸.xlsx`、`卫星加热器出图案例.docx`、`HZDX.SHX`、3 份代号 PDF、`加热器图纸.pdf`。没有业务实现代码。
- [source-files.json](source-files.json) 记录本次读取的原件大小及 SHA-256。B01 按此校验并复制到开发根 `fixtures/case/`，禁止重存原 Excel 或 CAD。源文件缺失时应从此原包恢复；不得拿另一项目的夹具替代。
- 未发现适用本地祖先 AGENTS.md；实施时重新读取当前路径规则。

## 2. 历史文档保留

目录 `C:\Users\HUAWEI\Documents\Codex\2026-11-06\d-ssh-5090-data-qmh-satellite\outputs`：

- `矩形加热器自动出图插件开发计划-v0.6.md`
- `矩形加热器自动出图插件开发计划-v0.8-简版.md`
- `矩形加热器自动出图插件开发计划-v0.9-审阅版.docx`
- `矩形加热器自动出图插件-执行参考.md`

本计划收敛其有效要求及后续决定，不覆盖这些文件。旧 Windows 执行端、自动跳过错误行、DWG 完全不作早期验证等说法被后续决定取代。原 `http://10.110.10.11/9999` 是路径；已核查的平台入口是 `http://10.110.10.11:9999/`，先前只到登录页，并未验证插件管理权限。

## 3. 5090 最新只读核查

SSH：`ssh -o BatchMode=yes -o ConnectTimeout=10 5090-qmh`。根目录 `/data/qmh/satellite-plugins-20261029`。

| 目录 | 2026-11-07 HEAD | git status 条数 | 边界 |
|---|---|---:|---|
| dsh-satellite-geometry | 50804c552366acc3b45e4ba92640f49eb4fe3fbe | 0 | 仅参考 |
| dsh-satellite-thermal | b8ea81ae1212f3cfd6da9a3b2af50281d3083378 | 0 | 仅参考 |
| microservice-refactor | 283a612693e50c02479f22f5a3cd371b9f053ff7 | 153 | 保留全部用户改动 |
| microservice-refactor-shared-core | 29fecb3bc55e114c766b1553b86d8adaa85dbca5 | 0 | 正在去重，不是本插件落点 |
| dsh-satellite-drawings | b84c22e888e5e3b3923bd1a2e4b508b0f6ac7c0b | 0 | 喷漆/多层，不同项目 |
| dsh-satellite-heater-drawing | 不存在 | — | 拟新增独立根 |

dirty 条数仅是 Git 可见项，不声明检查了 ignored 数据库等运行数据。此后其他工作可能推进，B01/B07 实施前再查；不得为符合上表重置仓库。

## 4. 真实源码锚点

以下 G 根为 `microservice-refactor-shared-core/dsh-satellite-geometry`：

| 现有路径 | 可参考内容 | 加热器约束 |
|---|---|---|
| G/plugin/package.json | 0.3.9；DSH bundle、client inject、ESM、MCP SDK、peer依赖 | 改为独立 ID；宿主实际版本另验，不照抄版本范围当兼容证明 |
| G/plugin/src/host-runtime.mjs | 从 profileContext.installAnchor createRequire 解析 Host 模块，fallback import | 保持 dsh-tools 等宿主 singleton 身份，不打包另一份运行时 |
| G/plugin/src/workspace.mjs | agentWorkspaces metadata与label兼容注册 | 使用 heater-drawing 身份，与 geometry 不冲突 |
| G/plugin/src/index.mjs、chat-bridge.mjs | 设置、凭据、会话、工具桥 | 移植机制后测试，不直接 import G 的私有文件 |
| G/plugin/mcp/server.mjs | stdio MCP、HTTP代理、严格参数 | 重写加热器工具契约，禁止任意绘图代码 |
| G/plugin/build.mjs | esbuild ModuleLoader、web/dist复制至public/viewer | 新包缺前端应硬失败，不能照搬“缺viewer仅warn仍打包”行为 |
| G/plugin/cordis.patch.yml | Cordis 注册 | 新 plugin/workspace/server/tool 命名空间 |

既有几何后端合并至 `microservice-refactor-shared-core/cad-assembly/backend/satellite_geometry/`；热服务为仿真链。两者均未证明提供本加热器的二维模板出图接口。本插件不引入 STEP/OCP/NX/CadSourceApi 模型绑定，不恢复旧 geometry 独立 Docker/service。既有去重进程继续由原项目处理。

## 5. DWG 可用性的新证据与限制

先前“未找到 ODA”的加热器盘点已经过时。当前读取 `dsh-satellite-drawings/docs/evidence/B04/capability.json` 与 `acceptance.json`：

- 已有 `.tools/oda-b04/oda-headless`，版本 27.10.0.0，headless runner `/usr/bin/xvfb-run`；ezdxf 1.4.5，Python 3.12.14。
- 报告记载真实 DXF→DWG→DXF 转换通过，13 个喷漆/多层小样实体；本次未重跑。
- `license_state=user_authorized_evaluation_only`，`production_deployment_approved=false`。
- `autocad_reopen=not_run`；acceptance status=blocked，缺实际 AutoCAD 编辑/保存/重开证据。
- adapter 源码在 `service/src/thermal_drawings/drawing/converter.py`，使用受控 argv、临时目录、进程组超时与许可记录核查。可参考结构，不导入其业务包或将它的 B04 批准范围转移给加热器。
- 另一项目还报告 QCAD 试用证据和 FreeCAD 失败路径；都不等于本项目/目标 AutoCAD 已验证。尤其 FreeCAD 曾出现单位×25.4、尺寸/中文语义损失，不能作为默认替代链。

B02 应优先核查已安装工具是否有适用于本项目的合法评估方式，再决定是否需要独立安装；生产包不捆绑未经许可的 ODA 或 SHX。不能因存在文件就宣称服务器具备完整 DWG 生产能力。

参考公开入口（本次未重新浏览）：

- ODA：<https://www.opendesign.com/guestfiles/oda_file_converter>
- ezdxf odafc：<https://ezdxf.readthedocs.io/en/stable/addons/odafc.html>
- LibreDWG：<https://github.com/LibreDWG/libredwg/blob/master/README>

公开文档证明候选入口，不证明许可证适用、无交互执行、中文与原生尺寸质量。LibreDWG 版本/对象限制须独立评估；不得因其开源就自动替换最终格式要求。

## 6. 不确定性归属

| 尚未实测 | 负责 Batch |
|---|---|
| 原模板实体、图层/块、字体覆盖、引线定量参数、纸框锚点 | B02 |
| 本项目 DXF→PDF 与 AutoCAD 2018 可编辑性 | B02小样、B09完整案例 |
| DWG许可与加热器小样转换/编辑 | B02，启用后B09/B10复验 |
| 登录后 DSH 注册、凭据配置、Host拓扑与安装权限 | B07/B10 |
| 最终环境资源、服务账户、端口、队列容量与备份窗口 | B10 |

以上事项有明确验证任务，不是开发完成事实；本次核查没有创建远端项目、改变旧仓库或安装任何组件。
