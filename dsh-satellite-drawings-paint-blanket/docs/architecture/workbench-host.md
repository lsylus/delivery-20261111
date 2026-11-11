> 当前补充：B07 host-r2 已按实际账号网关实现正式适配，见 [账号适配 ADR](host-account-r2.md)。下文 dev-only/未知身份描述属于原批次；正式平台验收仍待回执。

# B07 工作台与宿主边界

日期：2026-11-07，Asia/Shanghai。B07 实现两个独立包与共享工作台；正式宿主认证仍未配置，因此 B07 总体保持 blocked。隔离适配验收使用真实 B06/B08 服务，不消费 demo 作为 live 数据。

## 包和加载

`@satellite-drawings/paint-plugin` 与 `@satellite-drawings/blanket-plugin` 各带 cordis.patch.yml、打包后的服务端入口、宿主 client、MCP stdio、public 前端；分别注册 satellite-paint / satellite-blanket workspace、`satellite_paint_operation` / `satellite_blanket_operation` 工具及 `/api/satellite-{module}/service` 代理前缀。npm pack 产物无需源仓库的 packages 路径；React 由宿主 client loader 提供。未打包第二套 dsh-tools。需要加载共享宿主模块时，loadHostModule 仅通过 profileContext.installAnchor 解析；没有 anchor 明确报错。

隔离宿主提供 `satelliteDrawingsIsolatedIdentity.resolve(req,module)`，每次请求解析私有随机 HttpOnly cookie，返回 operator 登记的 owner/session/module 和服务间 credential；浏览器无法指定 owner、上游 URL 或后台 bearer。代理只向 loopback B06 发请求，逐次取身份，检查 Host、Origin、路径、方法和上传上限，不转发客户端 Authorization/X-Owner；写入必须同源。该 resolver 不是正式平台身份协议。未配置 resolver 返回 503；正式 issuer/audience/signature/key-discovery/subject mapping/revocation 仍须授权宿主适配，不能把隔离 cookie 当作正式登录验收。平台9999、旧插件及配置均未修改。

MCP 可用 operator 的 0600 `B07_MCP_CONTEXT_FILE` 启用同一隔离模式：mode=isolated-adapter、serviceUrl、identity{owner_id,session_id,module}、credential。每次调用从 B06 读取绑定/当前 revision，包装同一 OperationEnvelope 后调用 operations。工程包保存真实执行；未实现 drawing.export 等保持 503。未设置文件不自建身份，工具调用明确不可用。文件只在临时测试目录存在，不入包/浏览器/证据。

## 模型、选择与状态

LiveProvider 从 B06 当前 session binding 读取工程、revision、ModelSnapshot 与受控产物。下载 GLB 和 mesh-map 后核验 bytes/SHA256，并确认两者 ModelRef 一致。GLTFLoader associations 的 node/mesh/primitive 与 raycast triangle 必须精确命中一次 mesh-map；返回包含 occurrence、签名和模型 revision 的完整 FaceRef，不能用组件 ID 替代。

GLB 场景米/Y-up，拾取点显式回转为源 world mm/Z-up。三维 view_transform 为 GLB 场景到相机的行优先4×4矩阵；local_coordinates 为源 world-mm 拾取点。二维 fixture 为有标签的 DrawingDocument，矩形仅是面选择卡片，不代表几何投影、喷漆结果或展开计算。每个实体 source_refs 和 document.source_links 取真实本次 mesh-map。二维坐标为 fixture局部mm，view_transform 为 SVG局部到屏幕像素的行优先4×4矩阵；Shift框选返回与矩形区域相交的可见卡片引用列表及两个端点，不穿透隐藏三维面。此 fixture 不能导出生产图纸。

草稿键为 JSON 编码的 owner/session/project/module 四元组，并记录 revision；不同 revision 的草稿不恢复。保存参数/选择调用 B06 revisions 创建不可变新版本；视角只影响 Three.js 相机。草稿撤销重做只修改未保存草稿，不声称已实现后端 history.undo/redo。批注是会话草稿，未冒充持久工程几何。检查状态区分未保存、已保存、未计算；当前 B07 不读取/呈现 B08 保护区计算，二维始终显式 fixture。

聊天只调用宿主 inputActions.setDraft，不自动发送。校验 origin/source/白名单/request replay/session/module/project/revision/result/精确 FaceRef/有限坐标。每条有效来源消息重新读取服务端当前绑定、revision、mesh-map，再次核对身份和 head，避免外部修改后沿用缓存。异步消息串行处理；切 session 注销旧监听、使待处理回调无效，iframe keyed by session。模型/版本变化后旧引用拒绝。真实服务失败显示错误、不切换 demo，保留上个有效模型但禁止保存/聊天提交。

## 验收入口

NEW_ROOT 使用 `.tools/node/bin` 和 `.venv/bin/python`。`npm ci`、`npm run build --workspaces --if-present`、`npm run test --workspace packages/host-bridge`、`npm run test:e2e -- tests/e2e/workspace-isolation.spec.ts tests/e2e/model-selection.spec.ts tests/e2e/live-failure.spec.ts`、`.venv/bin/python scripts/verify_batch.py B07 --report-dir docs/evidence/B07`。

首次安装浏览器：`PLAYWRIGHT_BROWSERS_PATH=$PWD/.tools/playwright npx playwright install chromium`。e2e wrapper 为每个 spec 创建私有 B06、四个身份和真实 STEP 导入、独立端口及从 npm pack 解包的两插件；不启动正式平台。关闭服务的测试只杀该 spec 私有 PID。finally 停止 gateway/backend、验证端口关闭、清理私有凭据及数据，公开证据仅保存 hash、脱敏身份、HTTP 方法/路径/状态、截图和小型合成模型。

统一 runner 的可选 pre_commands 在pytest前执行，使从无构建产物的干净源码也会先完成 npm ci/build/typecheck；既有 Batch 无 pre_commands 时执行顺序保持。B07 formal-host.json status=blocked 是明确未满足的必需正式宿主检查，统一 runner 应 exit2，不能手改 passed。仅已通过隔离范围有 acceptance.json status=pass。

保留限制：B04 blocked/独立FAIL；最终 DWG 必须 AutoCAD 打开、编辑、保存、重开。没有大装配、ASM/PRT、生产部署或制造批准声明；未启动其他 Batch。
