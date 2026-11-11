# ADR-001：独立图纸服务与进程隔离

状态：B01采纳设计；部署由B15实施。目标Linux x86_64，NEW_ROOT `/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings`。G/T/S/H的代码、部署、路由、身份和数据不变。

两个独立插件包使用`@satellite-drawings/paint-plugin`、`@satellite-drawings/blanket-plugin`；workspace/MCP namespace分别satellite-paint、satellite-blanket。共享React/Three视图和host bridge在构建时进入包，运行时不查找源码相对路径。B01只有包入口，不会注册或安装到9999。宿主身份模块应从`profileContext.installAnchor`解析；不打包第二套dsh-tools。

一个新Python服务提供`/api/v1`，未来使用FastAPI/Uvicorn提供轻量HTTP；重型OCP/转换作业在独立受控worker进程中运行。首版并发1，服务调度冻结输入，worker拥有CAD对象生命周期，仅以资产引用/序列化文件跨边界，禁止向浏览器传pickle。run临时产物通过完整性检查和当前revision/fingerprint检查才发布，晚到结果仅入历史。B06必须验证超时、进程组取消、重启恢复和清理；B01无调度实现。

服务数据根、新端口、镜像和测试profile由B15在配置中登记并检查归属；example的18761不是占用声明。本批未启动监听服务，未访问生产业务会话。后端计划独立OCI镜像，内含新服务和geometry-core；转换器按许可独立worker/远程CAD服务提供。不能因许可未知就把SDK放入镜像。B04/B05核查工具、版本、许可和原生支持矩阵，B15核查分发条件。Python/CadQuery/Node的成功安装不等于商业工具可用。

只读源码盘点确认S的geometry_jobs依赖旧RequestProjectContext、geometry_bindings、JobStore及account数据，不整体复制。S的STEP/GLB序列化依赖旧file_sha256，由B02提取时解除。B01未提取任何几何函数。新的工程、owner/project授权、session binding和资产存储由B06实现；不使用旧数据库来获得快速假闭环。

Linux实测Python 3.12.14/CadQuery 2.8.0/OCP 7.9.3.1原生导入成功；不代表STEP/XCAF特征化通过。原系统Node为12.22.9，因此独立复制已有可信宿主工具Node 24.21.0到`.tools/node`，固定npm 11.19.0，未改系统PATH或旧仓库环境。Python依赖由uv 0.12.18完整lock，独立venv；精确版本及重建证据见B01/dependency-rebuild.json。

接口认证要求可信宿主签发身份和工程授权，不能信任任意X-Owner。代理前缀`/api/satellite-paint/service/*`与`/api/satellite-blanket/service/*`指向新服务；浏览器无后台静态token。CORS只约束来源，不承担认证。聊天和按钮后续共用OperationEnvelope白名单，尚未实现操作必须503，不以stub成功答复。
