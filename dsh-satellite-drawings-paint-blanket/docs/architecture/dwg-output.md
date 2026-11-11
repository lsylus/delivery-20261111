# B04 DWG 出图链路与交接约束

实现根：`/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings`，分支 `codex/thermal-drawings-b04`。B04 仅实现公共出图小样，不实现 B09/B12 业务、HTTP 发布或宿主安装。

## 公共接口

- `DrawingDocument(data)` / `.read(path)`：按打包的 C05 DrawingDocument v1 Schema 校验并复制输入；Schema 与 `contracts/drawing.schema.json` 的字节一致性有回归测试。拒绝非有限数、重复 ID、未声明图层、坏坐标系、退化/自交闭环、错误方向、越界/重叠孔。没有修改 B01 公共字段。
- `DrawingExporter.write_dxf(document, destination, profile)`：原生 LINE/ARC/CIRCLE/LWPOLYLINE/HATCH/TEXT/DIMENSION/POINT；先写临时文件、audit 与逐实体数值回读，再原子替换 DXF。二维点是 document.frame 中的局部 mm 坐标，不再次应用三维世界变换。frame/id/revision 保存为 XRECORD；实体 ID/revision/圆弧方向保存为 XDATA。完整 source_refs 仍在 DrawingDocument 中保留，不提供外部改图反推接口。
- `DwgConverter.capabilities()`：探测本机配置、可执行文件、Xvfb 和绑定工具 hash 的许可审阅记录；可用不等于已验证转换。`convert(dxf,destination,profile,document=...)`：独立临时目录、进程组、超时杀组、退出码、DWG 文件头和真实反向回读检查。所有条件满足后仅生成 draft candidate；返回 `needs_review`，`formal_artifact_published=false`。
- `validate_dxf`：读取实际实体，核对毫米、13 实体的类型/位置/半径/角度/闭合状态/图层/颜色/线型/孔环/中文/尺寸。公差 1e-6mm 只用于解析样图 oracle，不能当制造公差。尺寸为 ezdxf 实际生成的旋转线性 DIMENSION（type 0），端点方向对齐，保留原生可编辑对象及显示块；position 定义尺寸线偏移，不是任意文字锚点。

当前 profile：DXF R2018、DWG ACAD2018 / AC1032、`DroidSansFallbackFull.ttf`。CONTINUOUS/DASHED/CENTER 及 SOLID/ANSI31 明确支持；其他图案、线型、多行文字和未知参数明确拒绝。圆弧输入 rad，DXF 使用 degree；CW 交换几何端角，原始遍历方向留在 XDATA。HATCH 正常奇偶岛规则，孔环不变成实心阴影。

## 工具与许可边界

官方入口：<https://www.opendesign.com/guestfiles/oda_file_converter>。本批用户明确允许下载并运行 ODA File Converter；实际包为 27.10.0.0 Linux x64 AppImage。版本证据、分发包/二进制/启动包装器 SHA-256、官方重定向的脱敏 URL 见 `docs/evidence/B04/oda-download.json`。未发现官方独立校验和，计算 hash 只标识所下载内容，不能冒充发布者签名验证。

工具放在 `.tools/oda-b04`，不安装到旧服务、不打入 Git/OCI。AppImage 原样解包，包装器设置自身的 LD_LIBRARY_PATH/Qt plugins，系统已有 `xvfb-run -a` 提供显示；无需 FUSE、全局 Qt 或 root 安装。每次转换独立 XDG_CONFIG_HOME/XDG_CACHE_HOME，失败或超时不留下正式产物。包装器原文及环境在证据中保留。

包内 About 明示：`This software may not be licensed, sold, distributed or included with other software products without the written consent of Open Design Alliance.` 原文及 hash 已记录。当前许可记录仅为**用户授权的 B04 本地验证**；不是商业 SDK 授权，也不是生产服务器部署或再分发批准。B15 如要捆绑/再分发须取得 ODA 书面许可；生产非交互服务的使用范围仍需部署负责人确认，不从“免费可下载”推导完整部署权。

配置 `work/config/converters.local.json` 的 dwg 节使用 adapter=`oda_file_converter`、本机 executable、ACAD2018、实际字体文件路径、timeout_s 与非秘密 license_ref。未覆盖 native 节。`license_ref` 指向无密钥的审阅 JSON，含 decision/scope/reviewer/reviewed_at/tool_version/terms_reference/executable_sha256/tool_files；本批 evaluation scope 为 b04_local_evaluation，生产需要另行审核 scope。运行路径不作为浏览器任意命令入口。

替代方案：LibreDWG 是 GPLv3+ 开源工具，官网仍说明 writer 覆盖有局限；本批未把其未测试写入能力当替代成功。商业 ODA Drawings SDK/BricsCAD 需要各自许可及运行接口验证，未下载。已安装的 FreeCAD 0.19.2 实际使用 ODA 将 DWG 中转为 DXF；本批已尝试打开、将外轮廓宽度 100mm 改为 101mm、保存 FCStd/DWG 并重开。FreeCAD 将折线分解为边，未暴露原生可编辑 DIMENSION，输出重开出现 25.4 倍单位偏差（101→2565.4mm）。此替代路线不合格，不能作为独立原生 DWG 或 AutoCAD 验收。实际 inventory、文件 hash、退出码与操作脚本在 alternative-cad.json；LibreCAD 未在包清单中发现。

## 验收与失败语义

```sh
.venv/bin/python -m pytest -q tests/formats/test_drawing_document.py tests/formats/test_dxf_roundtrip.py tests/formats/test_dwg_adapter.py
.venv/bin/python scripts/probe_dwg.py --fixture fixtures/synthetic/drawing_sample.json --config work/config/converters.local.json --output work/runs/B04-dwg
.venv/bin/python scripts/verify_batch.py B04 --report-dir docs/evidence/B04
```

probe 在真实转换和反向实体核对成功后 exit 0，但结果 `needs_review`；缺工具/许可/字体 exit 3；实际转换失败 exit 1。runner 将登记的 exit 3 分类为 blocked，并保持非零总退出码 2。不能因为 pytest 通过或 DWG 文件头正确就通过批次。负向测试的伪进程只用于失败分支，不建立成功能力。

AutoCAD 审阅应保存 `autocad-reopen.json`，命名 reviewer/scope/revision_id/reviewed_at，记录实际 software=`AutoCAD`、software_version、license_evidence_ref、输入 DWG hash、edit 后不同 hash 的原生 DWG、截图/命令记录及各自 SHA-256。checks 中必须实际满足 open、holes_unfilled、chinese_readable、mm_scale、linetypes、editable_entities、edit_contour、edit_dimension、save、reopen_edited。`autocad-reopen.md` 给出当前未完成范围，不写假 approved JSON。

runner 的 probe 使用 `--reuse-reviewed`：如果已有人审阅，不重新生成带新时间戳的 DWG，而验证现有输入/输出/源码 hash 和原生 DXF 回读；旧审阅不符则 blocked。无审阅时执行新的真实转换。转换输入、fixture、源码、DWG/回读文件必须保持可读。新代码或新输入要产生新的候选和新的审阅，不能借用旧 approved。

B01 前置验收的源码 hash 对其测试提交复核；归档运行证据仍逐一对保留文件核 hash，不取代码提交中的验收前中间副本。这样后续合法修改依赖/registry 不会把已通过 B01 判为损坏；不会改写 B01 summary。

## 后续批次

B09/B12 消费同一 DrawingDocument/转换器，仅可把当前产物当未复核草稿；正式产物需通过 C03 检查与独立人工批准。AutoCAD 真正重开、修改轮廓和标注、保存再打开仍是 B04 的必需阻塞项。B02/B03/B06 按各自依赖可继续，本批没有启动这些批次。
