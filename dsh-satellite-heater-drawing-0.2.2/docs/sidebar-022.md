# 矩形加热器插件 0.2.2：原生右侧栏

目标宿主：`0.2.2-rc.1-102617d-dirty`。0.2.2 是本插件版本。

更新已安装的 heater bundle，按宿主提示重载并刷新会话。点击会话标题旁的
「矩形加热器出图」，工作台直接在当前聊天界面的原生右侧栏打开，不弹浏览器
新标签页。右侧栏页面选择列表也有同名入口；无会话时标题按钮禁用。
工作台使用同源 iframe 嵌入。折叠侧栏、切换会话保留已访问页面；关闭页签
释放该页。右侧栏的宽度、全屏与布局由宿主管理。

5090 安装包路径：

```text
/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/dist/plugin-release-20261110/qmh-dsh-satellite-heater-drawing-0.2.2.tgz
```

SHA256：`6999f02aaf6ae5cb98a8163ae5786b613d21dcac13c0b5c1b314bd6f190efbe9`

适配依据是当前宿主的 `sidebarRightTabs`、`sidebarRight` 和
`sidebar.right.pane.tab`，不以旧几何／热插件作为兼容性依据。
只需升级 heater，不要求升级 agent-page，也未改动宿主或其他插件。

开发验收通过：实际 tgz 客户端解包检查；使用当前宿主真实槽位核心、侧栏
类型注册器、导航控制器和状态存储，在 Chromium 中检查打开、重复打开去重、
折叠恢复、会话隔离、特殊字符编码、保留表单、关闭重开、无会话禁用、
420px 宽度、无新标签页和无脚本异常；5 项 Host 契约回归通过。

浏览器测试的外围聊天布局、侧栏外观和后端 API 是测试替身，截图不是实际
DSH 登录界面。真实 DSH 安装及登录 UI 尚未验收，不将开发检查标为现场通过。

包内仅 package.json、README.md、src/client.jsx、lib/client.js 与 0.2.1 不同。
81 个后台运行文件哈希一致，原 DWG/PDF 引擎仍为 0.2.0；本轮没有重新执行
完整 CAD 出图验收。包文件已授予 DSH 运行用户 xie 读取权限。
