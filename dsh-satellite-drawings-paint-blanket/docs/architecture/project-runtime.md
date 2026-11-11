> 当前补充：B07 host-r2 已按实际账号网关实现正式适配，见 [账号适配 ADR](host-account-r2.md)。下文 dev-only/未知身份描述属于原批次；正式平台验收仍待回执。

# ADR-006：持久工程与隔离开发服务

2026-11-07，B06。继承 ADR-001，未部署平台、未变更 G/T/S/H。真实宿主连接仍未配置；隔离 dev 验收不依赖该连接。

## 身份与权限

B01 的 `runtime.md` 要求通过 installAnchor 解析宿主模块、使用可信服务端身份，不提供签名格式、issuer/audience、密钥发现、session 生命周期或撤销协议。现有文档不足以声称宿主身份已接通。候选正式适配接口为 `verify(assertion) -> {issuer, subject, session_id, module, expires_at}`，须验证签名、audience、有效期、session 归属及撤销；subject 再映射服务 owner。B07/B15 在授权测试 profile 中核实该接口及代理边界。此处无猜测的 X-Owner 认证，也不装第二套 dsh-tools。

当前唯一可启动模式为显式 `auth_mode=dev-only`，监听地址限 loopback；`serve_dev.py` 绑定随机空闲端口，禁用代理头解析。每个请求核验真实 TCP peer、Host 和不带 Origin，避免把开发凭据用于浏览器或公网上。operator 在 0600 文件中登记随机 bearer 的 SHA256 与 owner/session/module；服务没有自助签发或客户端 owner_id 参数。数据根要求绝对路径、0700。凭据只用于本机服务间验证，不能据此对真实宿主宣称已认证。默认 disabled/host 均拒绝启动。

项目所有者由认证结果创建；外部看不到其他 owner 的项目、资产、模型、revision、run 和产物。写入还要求当前凭据 session 显式绑定该工程，绑定操作核对 session/module 和 expected_revision。相同 owner 的其他 session 可读所属工程，但不能读写另一个 session 的 binding，未绑定不能写。模块凭据不能操作另一模块的 run/revision/业务产物。源模型及其只读 STEP/BRep/GLB/映射允许同 owner 同工程明确共享；业务 revision、参数、保存包、当前结果分别保存。

## 持久化、版本与作业

独立数据根下 SQLite WAL，事务使用 BEGIN IMMEDIATE、synchronous=FULL。项目、不可变 revision、绑定、资产、模型、run、租约和产物均持久化，不使用进程 dict 作为工程或队列。revision UPDATE/DELETE 由触发器禁止；每次编辑/恢复新建 UUID revision，按 expected_revision 事务 CAS。模型未导入时 head 为 null；请求使用不透明保留值 `empty`，成功导入后创建具有真实 ModelRef 的初始 revision。新导入生成新的 model_id/revision=1，旧模型保留，不把 FaceRef 跨模型复用。

唯一 supervisor 通过数据根 flock 排他锁负责并发1队列。每个 run 冻结输入、fingerprint、工具版本及 request hash。相同 project/module/idempotency_key 重试仅在全部输入相同才复用 run；任何变化返回409，包括 operation/expected_revision。不要求重试时当前 head 仍旧，避免完成后重试重复导入。

native worker 使用当前独立 Python 的 `-I -m`，移除 PYTHONPATH/PYTHONHOME，每个作业新进程组，默认 timeout=120s、RLIMIT_AS=4096MiB（可配置）、禁用 core dump、BLAS线程1。HTTP线程不导入 OCP。Linux PDEATHSIG 与启动后的 parent PID 再检查覆盖父进程在 PID 登记前崩溃窗口。取消先持久化 cancel_requested，杀进程组并确认进程终止/回收后才 cancelled。失败/取消正式 artifacts 始终为空。重启核对 PID 与 /proc starttime，清理原 worker，将 running 记明确 service_restarted/failed，cancel_requested 完成取消；queued 保留并重新调度。不冒充从 native 算法内部续算。

worker只写私有 staging；文件 fsync、完整文件清单和逐项 SHA256/bytes 校验、schema及模型/GLB/FaceRef关联检查之后，在发布事务内验证租约与 state。目录同文件系统原子 rename 并 fsync 后才登记全部产物及成功状态，客户端不能列出半成品。数据库提交前崩溃留下的孤立目录重启清除；提交后的完整目录和登记保持一致。当前 head/fingerprint 未变才切换当前结果，晚到的完整结果仅入可授权查询的历史。stale 是 publication check 的 current=false，不是 worker state。取消与发布竞争由同一事务串行化：发布已完成时 cancel 返回 succeeded，未完成时取消获胜则不登记。

## 输入、产物与恢复

仅接收有上限的 raw 单文件 STEP，X-Filename必须简单 basename；先验文件头/结束标记，导入时再次验证完整源hash，并调用 B02 的唯一 `load_model_snapshot`。B02 对坏 STEP、外部引用和无面叶的明确失败保持。ZIP/其它压缩包全部拒绝，无解压功能，不接受本机路径、驱动器路径、百分号、反斜杠、.. 或 symlink。格式不是仅凭扩展名判定。默认64MiB为开发资源预算，不是大装配支持或用户SLA；B14大样本需要明确调整预算并实测。

每个导入发布真实 snapshot、definitions BRep、GLB和mesh-map。GET模型返回 snapshot 与受控 artifacts，Artifact增加可选 download_url；仅输出相对存储标识，下载重新授权并验hash，绝不返回任意绝对路径。B06只支持 mesh-map 中精确存在的 face selection，伪造/过期签名拒绝，其他选择能力由B07继续。

`engineering.save`从已持久 revision导出 EngineeringBundle JSON，包含源asset引用、派生BRep引用、模块/构造参数、历史revision链、rebuilder版本。尚无二维业务图时 drawing_document=null，不伪造 DrawingDocument、缝或点。`engineering.restore`仅接受本服务已登记且同工程同模块的工程包Artifact；读回校验后新建revision，保留其他模块状态。导出包是引用式工程状态，依赖本受控数据根中持久资产；不承诺离线复制单个JSON即可迁移所有二进制资产，也未实现任意外部工程包上传/解压。恢复后的参数仍可通过revision API修改。B11/B12补齐真实多层构造器、图纸及可继续编辑语义，B15负责完整数据根备份/迁移策略。

未实现的业务、DWG、ASM/PRT、undo/redo返回503/能力不可用，不创建成功假任务。B04保持blocked/独立FAIL，AutoCAD编辑保存重开仍为最终要求。

## 配置与验收

本批不提供永久公开开发账号。测试在0700临时目录生成随机凭据和独立SQLite，启动随机loopback端口，通过真实HTTP完成场景，最后停止服务/worker、验证端口关闭并清理凭据和数据。`scripts/serve_dev.py --config <private-config.json> --ready-file <private-ready.json>` 接受 Settings 字段；ready仅含host/port/pid。不要把config、bearer、原始大模型或整个数据根加入Git。

指定pytest覆盖幂等冲突、事务CAS、认证/session/module隔离、穿越和ZIP/超限、真实STEP、精确FaceRef、取消及进程组、崩溃/重启/超时、历史晚到发布、坏manifest/旧租约、两模块恢复。`check_b06_acceptance.py`归档真实HTTP产物与版本，`check_b06_isolated.py`在全新非editable安装后重复STEP+保存恢复重启，且未提供旧源码路径。统一runner另核对B02前置、schema和旧源码边界。该验收不等同宿主集成、制造人工批准或大装配性能验收。
