# B02 CAD 模板转换路线调查

日期：2026-11-08

## 结论

5090 起初没有现成的本项目 CAD/DWG 转换配置。进一步核查 ODA 官方 guest 下载与程序条款后，已在用户授权的一次性模板准备范围内，从官方 URL 为本项目独立下载 ODA File Converter 27.10.0.0，并完成一次原模板 DWG -> R2018 DXF 转换。没有复用另一项目的二进制或许可记录，也没有把工具加入 Git。

产品首发按用户决定继续 `DXF/PDF`，DWG 输出延期。一次性把原 `fixtures/case/CAD模板.dwg` 转为 DXF 是模板准备路线，不把产品 DWG 输出重新设为 B02 必需门槛。

## 5090 实际环境

- 主机：`5090-qmh`，Ubuntu 22.04.5 LTS，Linux 6.8.0-87-generic，x86_64。
- 执行身份：`uid=1004(qmh)`、`gid=1005(qmh)`，属于 `docker` 组。
- PATH 未找到：AutoCAD/`accoreconsole`、ODA File Converter、Teigha、BricsCAD、DraftSight、QCAD、LibreCAD、`dwg2dxf`、`dxf2dwg`、`dwgread`、`dwgwrite`。
- `dpkg`/`rpm` 未发现上述 CAD/DWG 产品包。
- Docker 已安装，但现有镜像清单没有声明为本项目授权的二维 DWG 转换器；通用 CAD/FreeCAD/几何镜像不能据名称推定可读写 DWG，也不能据存在推定许可适用。
- 调查开始时，本项目内没有 converter 配置或许可记录。现有 `docs/evidence/B02-fix-10/dwg/capability.json` 如实记录 fix-10 当时的 `not_configured`、`license_scope=none_for_this_project`、`conversion_run=false`；本次一次性模板准备不回写或冒充 fix-10 的产品 DWG 能力。

## 发现但不可直接使用的外部工具

另一项目 `/data/qmh/satellite-plugins-20261029/dsh-satellite-drawings` 内存在 ODA File Converter 27.10.0.0：

- AppImage SHA-256：`a73eea1dfc873cd46b94bfa07760dcff0082c4300dd33c5401e8a526cfab787b`
- 该项目 wrapper SHA-256：`591b2de0d13c48961b88c1fb0e5b61d68d1132431e08df2c46c76b09ef0134ca`
- 实际 ODA executable SHA-256：`03a219a6148852e7c8e5f7297a1c4c2e1cc992277580acc6111507ada342e6a8`
- 外部项目授权记录明确写为 `approved_for_evaluation` / `b04_local_evaluation`，`production_deployment_approved=false`、`redistribution_approved=false`。
- 其条款摘录明确禁止未经 Open Design Alliance 书面同意对软件进行许可、销售、分发或随其他软件产品包含。

因此该二进制及该项目授权都不转移到 heater-drawing，不复制、不调用、不入库。这一事实不等于 ODA 官方工具永远不可用于本项目，只表示当前发现的外部项目实例没有本项目可用授权依据。

## 官方候选与适用范围

官方来源：

- 产品页：`https://www.opendesign.com/guestfiles/oda_file_converter`
- 机器可读说明：`https://www.opendesign.com/guestfiles/oda_file_converter.md`
- 官方 guest 下载：`https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_11dll.AppImage`

官方 guestfiles 总页明确称 ODA File Converter 是 Windows、Linux、macOS 可用的 “free application”。产品页无需账户登录或点击接受协议即可取得下载重定向，并明确说明 Linux x64、GLIBC 2.28+ 与 AppImage 免安装运行方式。5090 是 Ubuntu 22.04、GLIBC 2.35，满足运行要求。

程序内 About 条款写明：未经 Open Design Alliance 书面同意，不得对软件进行许可、销售、分发或随其他软件产品包含。该限制禁止把工具复制进本仓库、交付包或产品部署；官方页面公开提供本地转换程序和运行说明，未要求账户或额外 click-through 协议，也未禁止本地使用。结合用户对一次性原模板准备的明确授权，本次只进行独立官方下载后的单机转换，不推断 SDK、服务器生产、产品 DWG 或再分发权。

独立下载事实：

- 官方 AppImage 版本：27.10.0.0
- 官方 AppImage SHA-256：`a73eea1dfc873cd46b94bfa07760dcff0082c4300dd33c5401e8a526cfab787b`
- 内部 executable SHA-256：`03a219a6148852e7c8e5f7297a1c4c2e1cc992277580acc6111507ada342e6a8`
- 保存位置：`/data/qmh/.cache/heater-drawing-b02-fix11/oda/`，仓库外缓存，不入 Git、不随项目交付。

## 一次性转换记录

- 输入：`fixtures/case/CAD模板.dwg`，SHA-256 `7c917bb7805aefd8ce327ca7f1e6912c2fcfabcb68ee91569f71503638c82676`
- 受控字体旁置：`fixtures/case/HZDX.SHX`，SHA-256 `42a8be6684d58bd2d886d7670d676af9445d65ca208ff116e8103b9114ed5f9c`
- argv：`xvfb-run -a env <ODA runtime paths> ODAFileConverter <isolated-input> <isolated-output> ACAD2018 DXF 0 0 *.dwg`
- 递归：关闭；audit/repair：关闭，避免转换器主动修复原件。
- 退出码：0；stdout/stderr：均为空。
- 输出：`docs/evidence/B02-fix-11/original-template/CAD模板-r2018.dxf`，320,518 字节，SHA-256 `9bcca3259ef7881af10e640538ec9cd8947bce7d86ee30f18e0c20f7cc8b4c15`

独立 ezdxf 读回：AC1032/R2018、`INSUNITS=4`（毫米）、audit 0 errors/0 fixes；模型空间 45 LINE、19 MTEXT、14 TEXT。原生 `HZ` 样式引用 `txt.shx + hzdx.shx`、宽度系数 0.7；这证明样式依赖在转换中得到保留，不等于已经完成目标 CAD 的字形显示验收。

原 DWG 原生外框约 200 x 282.857 mm；原 PDF 对应线框约为原生坐标的 1.042 倍。约 4.2% 差异由原打印/视口映射产生，不能复制到 Excel 权威加热片几何。新候选应使用原 DWG 的原生毫米分格和样式依赖，纸面放置另行受控。

一次性转换已经满足工具来源、身份、隔离目录、原 DWG hash 与日志要求。仍未完成的是：目标 CAD 实际显示/编辑、HZDX 字形显示、打印配置与字段填充后的工程验收；这些继续保持 pending。

## 字体初步事实

- 原 `fixtures/case/HZDX.SHX` 保持原字节，现有证据 SHA-256 为 `42a8be6684d58bd2d886d7670d676af9445d65ca208ff116e8103b9114ed5f9c`。
- ODA 转换链保留了 `HZ` 样式的 `txt.shx + hzdx.shx` 依赖，但当前还没有已确认可正确显示 HZDX 字形的目标 CAD/PDF 环境，因此显示可用性仍待验证。
- 再分发权未知只限制把字体复制进交付物或软件包，不能据此断言在已有合法 CAD 环境中受控使用也不可行。使用许可与再分发许可将在新候选决定中分开记录。

## 本阶段停点

本报告只封存环境与许可事实，不构成工程批准或 CAD 验收。正式具名工程审批保持 `pending`；本轮修正继续进行，不以当前未指定人员为阻塞理由。
