# 矩形加热器出图插件 0.2.2

DSH 安装此 tgz 后，重新加载插件，打开会话中的“矩形加热器出图”工作区。
基础聊天界面的会话标题旁提供“矩形加热器出图”按钮，点击在当前界面原生右侧栏
打开当前会话的工作台，不打开浏览器新标签页。右侧栏页面选择列表也有同名入口。
入口直接使用当前 DSH 的 sidebarRightTabs / sidebarRight 接口，不依赖 agent-page；
无会话时按钮禁用。侧栏折叠和切换会话时保留已访问工作台，关闭侧栏页签时由宿主卸载。
原有 agent-page 工作区注册作为可选入口保留。侧栏内嵌工作台使用同源 iframe。
选择工程师的 17 列 xlsx，设置合并文件名，上传并校验。全部行通过后点击
“生成 DWG 与 PDF”，完成后预览／下载。比例建议需要用户明确确认；错误行
先修正原 Excel 重传。可表达完整业务数据的排版错误可明确跳过，报告保留记录。
生成结果默认“待工程复核”，复核记录绑定本次文件清单。
比例建议须逐项选择后一次确认；不接受建议时修改 Excel 后重传。跳过行后
会重新检查剩余行，并重新确认比例。

插件内含独立后台源码、受控模板、锁定哈希的离线 Python 依赖；首次加载在当前
DSH profile 的 `satellite-heater-drawing/` 中创建专用环境和数据库。正常启动
不联网，不用 Docker，不导入其他插件代码。后台只监听随机回环端口，由插件
Host 注入真实会话身份；服务凭据不进入浏览器。卸载插件会停止本次后台进程，
保留历史输入和文件。首次启动可能需要一至三分钟。

5090 默认外部运行资源：

- Python 3.12：`/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/.python/cpython-3.12-linux-x86_64-gnu/bin/python3.12`
- CAD：`/data/qmh/OpenCADStudio/current/squashfs-root/usr/bin/OpenCADStudio`
- 工程师原字体：`/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/fixtures/case/HZDX.SHX`
- 系统 Noto：`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`

前三项可通过 Cordis config 的 `pythonExecutable`、`cadExecutable`、`hzFont`
覆盖（绝对路径）。默认资源适用于这台 5090；包中不携带 CAD、商业字体、
原始案例工作簿、用户数据或任何服务密钥。Node 要求 22.19+；目标 DSH
版本范围为 `>=0.2.2-rc.1 <0.3.0`，参考用户版本 `0.2.2-rc.1-102617d-dirty`。
离线依赖轮子适用于 Linux x86_64、Python 3.12；此包按 5090 环境制作。

输出：可编辑 DWG 2018、DXF、逐代号 A4 PDF、按 Excel 行序合并 PDF、
原表和实际表、行报告、哈希清单、CAD 验证报告及 ZIP。PDF 从最终 DWG
重新打开后打印，再独立重开重打比对；失败时不发布部分集合。打印外观沿用
样例约 4.2% 放大。中文用原 HZDX，TXT 数字轮廓因内置替代字体可能略有差异。

对话提供 `heater_capabilities`、`heater_job_status`、`heater_explain_issues`、
`heater_open_workspace` 四个受限工具。上传、生成、比例／跳过／人工复核通过
工作台执行；对话工具不签发确认回执，不接受任意文件路径。

本包开发验收与真实 DSH 安装验收分别记录。不把未执行的安装测试、AutoCAD
复开或工程师正式审批标成通过。精确验收范围及 tgz 哈希见随包外部验收报告。
