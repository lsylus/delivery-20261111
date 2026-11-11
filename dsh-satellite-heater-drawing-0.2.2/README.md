# 矩形加热器自动出图插件

从工程师规定结构的 Excel 批量生成可编辑 DWG、DXF、逐代号 PDF、合并 PDF
及可追溯的出图清单。PDF 从最终 DWG 重新打开后打印，并执行独立复开检查。
当前插件版本为 **0.2.2**，适配目标为 **DSH 0.2.2-rc.1-102617d-dirty**。

在当前会话标题区点击「矩形加热器出图」，工作台嵌入 DSH 原生右侧栏。
使用当前宿主的 `sidebarRightTabs`、`sidebarRight` 和 `sidebar.right.pane.tab`，
无需先安装 0.2.0 或 0.2.1。侧栏内工作台采用同源 iframe。

## 目录

| 目录 | 内容 |
| --- | --- |
| `plugin/` | DSH Host 适配、客户端侧栏注册、打包配置、离线启动器 |
| `service/` | Python 出图服务、输入校验、任务存储、CAD 和 PDF 验证 |
| `web/` | 工作台页面、上传、任务、确认、预览和下载 |
| `templates/`、`schemas/` | 受控模板与业务数据约束 |
| `tests/`、`scripts/` | 回归测试、检查、生成与构建脚本 |
| `docs/` | 设计、使用和验收范围说明 |
| `dist/plugin-release-20261110/` | 本地保留的 0.2.0／0.2.1／0.2.2 完整包，默认不提交 Git |
| `fixtures/case/` | 本地保留的工程师案例及原字体，默认不提交 Git |

本交付复制当前工作文件，包括原仓库中尚未提交的实现；不携带原 `.git` 历史。
未复制虚拟环境、node_modules、工具缓存和旧的大型调试输出。
复制清单和校验结果见 `handoff/`。

## 运行要求

- Linux x86_64；Node.js 22.19+（具体范围见 plugin/package.json）；Python 3.12。
- 可用的 OpenCADStudio；DWG/PDF 生成需要其原生保存、复开和打印能力。
- 工程师的 HZDX.SHX 字体及系统 Noto 字体；CAD、Python 解释器和字体未封装进 tgz。
- DSH 插件参数 `pythonExecutable`、`cadExecutable`、`hzFont` 可指定绝对路径。
  5090 上的默认路径和使用方法见 [插件说明](plugin/README.md)。

## 构建

在 Linux 下准备 Node/npm、uv 和 Python 3.12 后，从仓库根执行：

```bash
bash scripts/build_release.sh
```

此命令按 `service/uv.lock` 和 `plugin/package-lock.json` 构建，下载锁定的
Python wheels，然后生成离线运行目录及 tgz。复制的离线 wheels 可用于本地重建，
但它们默认被 Git 忽略，新的 GitHub 克隆需要联网恢复依赖。
完整包可直接首次安装；0.2.1 为打开新网页的入口，0.2.2 为原生右侧栏入口。

Host 契约检查：

```bash
node --test plugin/tests/host.test.mjs
```

Python、CAD、原案例及本机宿主集成测试的依赖和边界，见
[原开发说明](DEVELOPMENT.md)、[原生 DWG/PDF](docs/native-dwg-pdf.md)
及 [发布说明](docs/release-0.2.2.md)。部分历史检查脚本保留了 5090 绝对路径，
迁移时需配置相应宿主和浏览器依赖。

## 验收状态

已完成真实 OpenCADStudio 出图引擎的开发验收，以及当前 DSH 侧栏接口和
Chromium 交互验证。侧栏测试使用真实宿主注册器、控制器和存储，外围页面和
API 为测试替身；不把它等同于已登录 DSH 现场验收。

用户曾确认 0.2.0 在原部署中安装可用。2026-11-11，9999 部署变化后报告
安装结果丢失且列表中没有 heater；0.2.2 在该部署的安装问题尚未解决。
三个包均约 73.94 MiB；源码中的账号私有安装器有 64 MiB 限制，但尚未确认
用户此次安装是否走该通道。不要把构建通过写成当前 9999 安装已通过。

## GitHub 提交范围

源码已配置 `.gitignore`：tgz、运行依赖、原始工程师案例、历史原始证据和本机
状态不进入默认源码提交。三个 tgz 及 SHA256 在本地保留，发布时可作为
GitHub Release 附件；本次仅准备文件，未创建远程仓库或上传内容。

受控模板和规则属于本项目功能的一部分，保留在源码中。没有擅自添加开源许可；
第三方运行依赖和外部 CAD、字体沿用各自的许可。见
[第三方与外部资源](THIRD_PARTY_NOTICES.md)。
