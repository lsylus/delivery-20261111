# B07 host-r2：已知账号网关的正式适配

状态：实现进入正式路径；等待平台私有安装、真实登录验收与独立复审。原 B07 FAIL、host-r1 candidate-only 结论保留。本文件补充 B06/B07 ADR，覆盖旧文档“仅 dev-only 可启动 / 正式身份来源未知”的当前描述，不改写历史证据。

## 绑定依据

用户明确提供 9999 启动关系并授权本轮适配。只读来源为 `/data/wqn/xingqiao-agent/start.sh` → `/data/lbk/codex_web/deepseek-harness2` → `/data/lbk/codex_web/deepseek-harness-no-history`，DSH `0.2.2-rc.1`，部署 Node `22.22.2`。真实源码的 gateway 验证登录 session 并转发到按 account 分离的 Host；账号 home 为 `users/sha256(userId)/home`。`private-plugin-context.json` 是网关生成的非秘密上下文。来源事实和哈希另见 host-r2 报告/证据；这里不声称本轮已登录线上 9999。

## 三层授权

1. 真实 account/profile：只读取 `profileContext.home` 下的上述私有文件，校验 regular file、0600、home 路径、账号 hash、实际 DSH 包版本。固定 tenant 为 `xingqiao-9999`，owner 为 SHA256(tenant + NUL + userId)，不是 browserPeer UUID。平台实际部署是“一账号一 Host”；不声称同一 Host 内有多自然用户隔离。
2. live chat session：浏览器请求由真正 `connection.requestRejection/admit` 认证且必须为 browserPeer。`x-satellite-session` 只是选择器；需在本账号 `SessionStore` 中查到活对象，并逐次复核对象相等及生命期。原生工具仅使用可信 `exec.agent.id/session/signal`，不接受模型参数作为身份。插件卸载关闭 callback server、取消请求并清除 pending。
3. drawings project：新服务工程为 owner-only，不接管平台已有工程。每次读写检查 SQLite 中 owner、session binding、固定 module；间接 run/artifact 先反查 project/module。可用新表 `host_project_access` 将权限降低为 read 或 deny；缺省为创建者 write。不存在跨用户共享授权。只读用户可绑定自己已有工程的元数据，后续写操作仍拒绝。所有本轮新工程名限定 `TEST-qmh-`。

## Host 与后端

正式 `dsh-account` 模式独立于 dev-only，互斥凭据配置，监听 loopback，拒绝浏览器 Origin、Authorization bearer 和非 loopback TCP/Host。每模块经 DSH credentials service 创建持久 Ed25519 私钥；只输出公钥登记信息。后端 operator 显式登记 tenant/user/home_hash/module/public_key/kid，凭公钥确定 owner。

断言绑定 method、规范 path、原始 body SHA256、Content-Type/X-Filename、module、session、nonce、callback port 和不超过 15 秒期限。后端验证签名、限量一次性 nonce，再回调 127.0.0.1 的 Host 临时端口；Host 对仍有效的请求/会话签名答复。后端复核回调签名、期限和 registry 未被撤销。回调无效/超时、Host 重启/卸载、会话销毁、签名被改或后端中断均 fail closed。重启后持久 key 可继续使用，旧 pending 不复活；网关的登录撤销仍遵循平台已有请求复核/流关闭及轮询行为。

已获授权并开始执行的几何任务不会因稍后退出登录自动取消。授权检查与提交之间不是跨进程事务；撤销保证后续授权请求拒绝，不承诺撤销前已通过授权的操作可回滚。任务取消使用本模块 run 工具，不能把 run_id 当成功。

## 安装和工具

两包独立 insert-only IDs；原生 DSH 模块由实际 installAnchor 提供，不打包第二套 dsh-tools。实际 Cordis 要求异步 apply 才能等待初始化；对象参数明确 additionalProperties。原生工具为每模块 `host_status`、`operation`、`run`。原隔离 MCP 脚本保持显式 isolated-adapter 配置，正式使用 DSH 原生工具，不把隔离 bearer 接入正式链。

安装需要平台对精确 TGZ SHA256 作 operator approval；只允许平台将包复制到 qmh 的 dev_agent workspace 后用 `private_plugin`。平台在安装/刷新前确认 qmh 无需保留的运行任务。执行方没有修改 live profile、刷新 /agent 或重启平台。

## 验证边界

本轮使用实际 DSH Connection、SessionStore、ToolsService、账号 gateway、private installer/CLI，加载真实 TGZ，并通过 Python HTTP/worker 和浏览器渲染验证。登录库、credentials provider、session/agent exec 和 UI slot 容器为合成夹具；它们不等同线上账号持久化、模型实际 tool 执行器或完整 `/agent` 页面验收。所有写入在 `/data/qmh`。线上登录、两聊天/两模块切换、真实平台私有 credentials 持久化和最终权限撤销仍需平台回执与独立复审。
