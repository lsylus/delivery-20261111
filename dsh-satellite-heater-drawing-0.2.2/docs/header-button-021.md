# 加热器插件 0.2.1：会话标题按钮

只升级 heater 自身，不修改 agent-page 或其他插件。基础聊天 UI 的会话标题旁
增加“矩形加热器出图”按钮，点击在新标签页打开当前会话的工作台。
不依赖 custom.agent 槽位提供者；原有工作台标签注册保留。无会话时按钮禁用。

5090 包路径：

`/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing/dist/plugin-release-20261110/qmh-dsh-satellite-heater-drawing-0.2.1.tgz`

在插件管理器更新已安装的 heater bundle，按宿主提示重载，再刷新会话页面。
本轮未代替用户安装到真实 DSH，包中按钮不会在旧 0.2.0 安装上自动出现。

验证：实际 tgz 解包客户端检查通过；真实 Chromium + React + 仅基础槽位
测试宿主中验证按钮显示、点击打开当前会话、新会话地址更新、特殊字符编码、
无 opener、无会话禁用及无 JS 错误。目标宿主是 0.2.2-rc.1-102617d-dirty；
尚未在其真实会话页面观察升级后的按钮。

包差异只有 package.json、README、client.jsx 和编译后的 client.js；
81 个后台运行文件及 DWG/PDF 引擎与已验收 0.2.0 完全一致，本轮没有重复执行
完整 CAD 出图流程。后台能力接口仍报告原出图引擎版本 0.2.0。

SHA256：`ed4df1504dfee18e92814036fe19296597ce4ae682920457cf7db1b671b9be51`
