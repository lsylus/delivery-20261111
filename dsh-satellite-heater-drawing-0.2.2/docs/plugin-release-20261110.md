# 5090 插件包开发验收：0.2.0

交付物为真正的 npm 插件 `@qmh/dsh-satellite-heater-drawing@0.2.0`，不是源码归档。
用户本轮明确要求交付 5090 上的 tgz，并接受不执行真实 DSH 安装测试。
最终验收结论和包 SHA256 以
`docs/evidence/plugin-release-20261110/summary.json` 为准；该文件只在最终 tgz
的解包端到端测试全部通过、包哈希一致后生成。

5090 交付目录：

```text
/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/dist/plugin-release-20261110/
  qmh-dsh-satellite-heater-drawing-0.2.0.tgz
  SHA256SUMS.txt
  acceptance-summary.json
```

## 功能和使用

安装 tgz、重新加载插件后，在 DSH 会话工作区选择“矩形加热器出图”。上传工程师
提供的 17 列 xlsx，设置合并文件名，通过检查后生成。包内含客户端、工作台、
独立后台、受控模板、锁定哈希的离线 Python 轮子和离线 PDF.js 预览资源。
首次加载会在当前 DSH profile 创建专用 venv、数据库、输入和产物目录，不修改
其他插件环境，也不要求 Docker 或联网下载运行依赖。

输出可编辑 DWG2018、DXF、3 张案例单页 PDF、按 Excel 行序合并的 PDF、
原始表、实际表、行报告、CAD 验证报告、哈希清单和完整 ZIP。后台会重新打开
最终 DWG、反向导出 DXF 做语义验证、从 DWG 打印 PDF，并独立重打比对。
只有完整集合通过后才发布下载。

业务数据以 Excel 为准（动量轮标审为“郑玲”）；使用本套图框和字段结构；
打印外观保留样例约 4.2% 放大。TXT 原字体缺失，使用 CAD 内置替代字体，
数字轮廓可能略有差异，不宣称与 AutoCAD 样例逐像素一致。

字段非法时修正 Excel 重传，不构造替代值。完整业务行的版面错误可以明确跳过；
比例建议逐项选择后一次确认；不接受时修改 Excel 重传。跳过行后重查剩余行，
原比例确认重置。禁止跳过全部行。确认回执绑定 owner、session、job、revision、
精确清单和有效期；复核记录再绑定 run、manifest 和文件哈希。自动出图结果仍为
“待工程复核”。自动化测试中的 rejected 复核记录用于验证流程，不是工程结论。

对话注册四个受限工具：`heater_capabilities`、`heater_job_status`、
`heater_explain_issues`、`heater_open_workspace`。上传和确认通过工作台执行。
任务和下载按真实会话隔离，取消不发布部分产物，重启恢复历史，异常中断可重试。

## 验收范围

- 176 项存储、契约、Excel 回归通过，其中包含幂等并发、隔离、回执重放／篡改、
  不完整结果禁止发布、下载重哈希、旧 run 禁止复核、异常状态恢复。
- 2 项真实 CAD 决策集成测试通过：混合版面错误先跳过再确认比例；伪造集合和
  全部跳过均被拒绝，原工作簿保持不变。
- 5 项 Host 测试通过，覆盖可信会话、工具身份、同源防护、回执、工作区身份。
- 从最终 tgz 解压校验客户端模块加载、导航、工作区、会话切换重挂载和无会话状态。
- 从最终 tgz 解压，在全新临时 profile 离线创建环境，运行真实后台、真实
  Chromium 工作台、真实 OpenCADStudio 出图；Host 服务接口使用认证 mock，
  没有声称运行了真实 DSH 安装。
- 端到端检查上传错误文件、正常 Excel 校验、取消／重试、DWG／PDF完整生成、
  对话工具、跨会话拒绝、禁止直接提交确认、下载哈希、PDF 画布实际墨迹、翻页、
  下载、宽窄布局、过期批次复核拒绝、签名复核记录和重启持久化。
- 对完整 3 页 PDF 用 Poppler 渲染并目视检查，核对图框、尺寸、引线、技术要求、
  标题栏与页脚；最终包 PDF 仍执行原生语义回读和独立重打比对。
- tar 文件清单审计及每个 runtime 文件 SHA256 通过；无原始案例 Excel、SHX
  字体、私钥、任务数据库、node_modules 或 venv。Python 编译、JS 语法和
  `git diff --check` 通过。

未执行项：用户真实 DSH `0.2.2-rc.1-102617d-dirty` 安装／重载；AutoCAD
复开；工程师正式加工审批。历史 B06/B07/B08 的原计划全量验收与本次精简实现
分别记录，不把旧计划全部门槛标成 passed。

## 环境边界与接口

包面向 5090 的 Linux x86_64、Python3.12、Node22.19+；目标 DSH 版本范围
为 `>=0.2.2-rc.1 <0.3.0`。默认外部资源和覆盖配置见 `plugin/README.md`。
CAD、基础 Python、原 HZDX.SHX 和系统 Noto 字体保持为 5090 上的外部资源，
应保留现有路径。包不是 Windows CAD 运行包。

服务由插件生命周期管理，使用标准库回环 HTTP 服务和 SQLite 单队列；本版
不创建 systemd 服务。私有 API 前缀 `/api/heater/v1`，浏览器只走认证 Host
`/api/satellite-heater`。上传为原始 xlsx body、指定 MIME 和 URL 编码
`X-Heater-Name`，不是历史 OpenAPI 规划中的 multipart。实际接口以
`service/src/heater_drawing/app/server.py` 和 Host 路由为准；历史
`schemas/openapi.json` 不代表本版全部实现。

## 重建与复验

在工程根目录使用现有 `.venv` 和 Node22（系统 Node12 不适用），保持 lockfile：

```sh
.tools/uv export --project service --frozen --no-dev --no-emit-project --format requirements-txt --output-file dist/heater-runtime-requirements.txt
# wheelhouse 已由 Python3.12 的 pip download --require-hashes --only-binary=:all:
# 基于以上 requirements 准备在 dist/heater-wheelhouse；首次准备需要联网。
.venv/bin/python scripts/prepare_plugin_runtime.py
# plugin 中用 Node22 对应 npm ci 安装锁定开发依赖，然后回到根目录。
node plugin/build.mjs
# 在 plugin 目录执行 npm pack --pack-destination ../dist/plugin-release-20261110
node scripts/check_packaged_client.mjs dist/plugin-release-20261110/qmh-dsh-satellite-heater-drawing-0.2.0.tgz
HEATER_TEST_CHROMIUM=/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings/.tools/playwright/chromium-1208/chrome-linux64/chrome node scripts/smoke_packaged_plugin.mjs dist/plugin-release-20261110/qmh-dsh-satellite-heater-drawing-0.2.0.tgz fixtures/case/加热器图纸.xlsx dist/新的验收目录
```

Playwright 仅供开发验收使用，运行插件不依赖参考项目。正式包 SHA256、文件
清单及本次日志在对应 evidence 目录，最终包副本和报告同时复制至本地 outputs。


## 9999 安装路径访问修复

2026-11-10，确认本机 127.0.0.1:9999 经 SSH 转发到 5090 的 10.110.10.11:9999，
DSH 进程 UID1001（xie）。原交付目录 dist 和包文件不允许该账户读取，导致
安装器的 existsSync 返回 false，并显示“该路径不存在或不是有效的插件包”。
已为 xie 增加包路径及外部 Python／CAD／HZDX 字体必要的只读／执行 ACL；
逐项验证其他主体的原有效权限和特殊目录标志不变。以 UID1001、group1003 在
只读绑定目录中完成内核实际访问检查，包哈希一致，3734 个运行文件可读、
248 个目录可进入。未执行用户 DSH 安装。原 tgz 和 SHA256 不变。
证据：docs/evidence/installation-access-20261110/summary.json。
