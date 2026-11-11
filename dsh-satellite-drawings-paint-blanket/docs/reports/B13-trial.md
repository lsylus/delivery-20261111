# B13 R4 独立试用环境

2026-11-09（Asia/Shanghai）12:27 已启动并验证，后台持续运行。试用入口：**http://127.0.0.1:18843/trial**。先打开该入口建立隔离试用会话，再点击“打开多层工作台”；直接工作台地址为 http://127.0.0.1:18843/satellite-blanket/?session=b13-r4-trial 。

身份为 **B13-TRIAL-ISOLATED / b13-r4-trial**，dev-only / isolated-adapter，不是正式DSH/9999登录。本机各浏览器使用同一个专用试用身份及工程绑定。关闭网页或SSH隧道不会删除远端数据；服务未设自动到期。远端主机重启后需手动启动，子服务异常退出由专用supervisor重新拉起。

## 示例与从零操作

本地示例绝对路径：`C:/Users/HUAWEI/Documents/ChatGPT/插件/work/b13-trial/B13-TRIAL-motor.step`。入口页也可下载。由已审查源码内`fixtures/real-derived/b13/motor.brep`完整44面设备重新导出，与截图同源；没有读取或复制历史验收图片、工程或证据。示例SHA256：`153ebc2cf705cf045e57d7d7ce6612a53a3aba6d943d951dadcbcb34f708d53d`。

1. 打开入口，点击“打开多层工作台”→“新建工程”→“导入 STEP”。允许上传自己的单文件STEP，上限64 MiB。
2. 示例策略选“完整设备正间隙多面罩形”，目标面选`face-4`，点击“设为安装底面”。
3. 安装X参考面选`face-27`（法向约1,0,0），旋转0，原点“本实例投影范围最小角”，XY偏移0。点击“核对安装坐标与分段范围”。
4. 间隙1 mm，安装X分段填`40,300,334`，点击“生成罩形”。两侧控件区可滚动，运行需等待。
5. 点击“预览15mm连接方案”，再“执行修改”。示例预期34制造面、33片、75条15mm搭接及1折叠；二维图可缩放/平移。
6. 选择裁片、固定点或接缝后编辑，先“预览”再“执行修改”。完成后“保存工程包”，可“恢复工程包”或“导出 DWG 草稿”。刷新会重载当前工程，同浏览器保存的恢复入口位于本地存储中。

面号和分段值仅适用于此示例。自有STEP须按其几何选择支持底面、实例、方向及范围，不能照搬。更改安装坐标会使旧分段和净片失效，需要重新核对及生成。工作台不预载截图中的历史工程。

## 已审查版本与隔离边界

启动前主树和原审查树均为`49622b1cf0245f64a1bad5dbe419e5277c8c52e4`且clean；未发现适用AGENTS.md。已读最新`docs/reviews/B13-r4.md`：R4声明技术范围独立PASS，B13整批仍in_progress / blocked、full_acceptance:false。本次不恢复总goal/B14/B15，不创建其他聊天，不修改业务实现，不做新一轮大回归。

专用根：`/data/qmh/b13-r4-trial-20261109`。`code/`从该提交按源码/契约/夹具路径导出，349个核对文件与Git字节相等，不读取历史证据。专用venv链接已有依赖，只加载snapshot内service/geometry源码，包括隔离worker的`-I`启动。前端从snapshot构建，专用host适配只新增隔离试用入口和示例下载，产品源码未改。所有新增文件、临时、缓存、日志和数据均在/data/qmh，未修改HOME或全局环境。

数据根：`/data/qmh/b13-r4-trial-20261109/data`（0700）。后端监听127.0.0.1:18844，host监听127.0.0.1:18843；Windows隐藏SSH将本地127.0.0.1:18843转发到远端同端口。未使用/停止B07的18777，未改B07树、配置、注册表、9999、旧几何/热系统、B12保留文件或既有数据库。

DWG只引用既有受控converter配置，不复制或披露内容；配置SHA256为`5819ebeb45883b9108cbef9b7414f96dd273819f9d821b6a3ffd1091cc71cec9`。仅提供既有允许的DWG草稿转换，不声称AutoCAD重开验收。并发1，每个原生作业超时300秒、内存上限4 GiB；支持单文件STEP，ASM/PRT仍不可用。

## 进程与停止恢复

启动记录：supervisor PID 2727214（start_ticks 3111574376），backend PID 2727215，host PID 2727216，Windows隐藏SSH PID 30324。子进程重启后PID可能变化，以远端`state.json`及本地`tunnel-state.json`为准。

远端查看、停止、恢复（分别运行；只作用本轮supervisor及子进程，保留数据）：

```powershell
ssh 5090-qmh "/data/qmh/b13-r4-trial-20261109/venv/bin/python /data/qmh/b13-r4-trial-20261109/control.py status"
ssh 5090-qmh "/data/qmh/b13-r4-trial-20261109/venv/bin/python /data/qmh/b13-r4-trial-20261109/control.py stop"
ssh 5090-qmh "/data/qmh/b13-r4-trial-20261109/venv/bin/python /data/qmh/b13-r4-trial-20261109/control.py start"
```

本地隐藏SSH管理（核对PID和启动时间，端口被其他进程占用时拒绝覆盖）：

```powershell
& 'C:/Users/HUAWEI/Documents/ChatGPT/插件/work/b13-trial/tunnel.ps1' status
& 'C:/Users/HUAWEI/Documents/ChatGPT/插件/work/b13-trial/tunnel.ps1' stop
& 'C:/Users/HUAWEI/Documents/ChatGPT/插件/work/b13-trial/tunnel.ps1' start
```

精确转发命令：`ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:18843:127.0.0.1:18843 5090-qmh`。不要重复占用同端口；恢复后先打开/trial建立浏览器会话。

## 启动检查与能力限制

Windows本地入口HTTP200、工作台HTML200、context200且身份正确。实际Chromium经入口可见链接打开LIVE工作台，新建工程按钮可用，无pageerror；认证health和capabilities均200。检查未创建测试工程或修改用户工程。运行记录和截图在专用根`connectivity.json`、`trial-browser.png`，本地副本在`work/b13-trial/`；不是新一轮验收证据。

自有服务及隧道保持后台运行。试用运行状态不改变B13制造/完整验收blocked：球端制造标准、motor安装/开口/间隙/接口分类，以及AutoCAD、原生格式和正式平台验收仍需完成。任意复杂自由曲面不保证可生成。无需正式平台账号，是明确标识的隔离演练。

收尾说明：组合式启动/文档写入命令曾被工具策略拒绝；拆为单独启动和文件补丁后完成，不影响已运行试用。没有因此增加回归或历史归档范围。调度器也已确认本地入口HTTP200并向用户提供链接。
