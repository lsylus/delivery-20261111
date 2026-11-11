# 局部特征组合包络 v1：使用与验证记录

在本机浏览器打开 `http://127.0.0.1:18890` → “多层图纸”，查看已载入的 motor。点击“聚焦定位标记”后直接拖动，松开保存；再点击“导出并预览 DWG 草稿”。需要换点时点击“下一个定位标记”。

插件 **0.3.0** 的 tgz 需要配套 Python/OCCT 后端、OpenCADStudio 与 converter 配置，tgz 本身不独立执行几何计算。本试用已配置 `deploy/opencadstudio-5090.json`。

本报告对应 `feature_composite_v1`，插件版本为 **0.3.0**。本轮新增平面自动合片、真实折痕/直边搭接，以及圆柱端盖和平台根部的分瓣舌片草案。完整电机的真实 UI → 原生展开 → DWG 导出 → 原软件回读与位置标记拖动审计已通过；刷新和工程保存/恢复均保留同一持久点的新位置。该结论是数字几何和可编辑草稿流程通过，不等于分瓣舌片的材料制造行为已经批准。

## 使用方式

试用服务为 `http://127.0.0.1:18890`，插件入口为“多层图纸”。远程服务需通过 SSH 转发本地 18890 端口。启动命令为 `scripts/start_simple_trial.py --converter-config deploy/opencadstudio-5090.json --background`。正式 DSH 宿主身份部署不在本试用结论内。

导入完整 STEP，选中整个设备/模块后生成局部圆柱、方盒组合，默认包含其附带结构；只有明确指定不包覆的部分才排除。平面相邻面会在无二维重叠、无折痕环的条件下自动合片，未合并直边生成真实搭接；圆周接口生成 `segmented_fan_tabs_v1` 分瓣舌片和接收区。界面默认每层独立裁片上限为 10；超限时保留候选并说明未满足项，由用户明确调整上限后继续，不静默省略凸出结构。电机本轮合片后为 19 片，不承诺必须降到 10 片。

当前安装面仅作为 reference；完整外皮未自动开底（installation_opening=false），未自动固定底部（bottom_fixed=false），需另行设计审核。

裁片展开后，先点击“聚焦定位标记”，需要切换时点击“下一个定位标记”，再直接拖动并松开保存；聚焦操作会围绕目标片料放大居中。

固定点为位置标记，实际 DWG 使用可编辑 POINT 实体，不代表钻孔。拖动后应保存同一个持久 point_id 的面内坐标，刷新/恢复仍保留新位置；二维点位通过面展开与排样两次刚性映射落入最终图纸。拖动位置标记不得改变 CUT 裁切轮廓。

## 本轮验收对象与证据

电机原始 STEP：`docs/evidence/B13/r4-review/run-01/complete-motor.step`。真实 UI 流程证据集中在 `work/feature-composite-evidence/`，包含 `workflow.json`、拖动前后及恢复后的完整 NetResult、UI 实际导出的两份 DWG、界面证据。下列实测数值来自本轮新工程与绑定的实际 DWG，不引用旧单罩或占位生产样本。

独立检查脚本读取实际 DWG2018 字节，通过 OpenCADStudio `--serve` 原生打开、审计、反存 DXF，并严格核对源 DrawingDocument 的全实体、轮廓类型、文字、可编辑尺寸、元数据与 XDATA。另直接重算持久固定点坐标；比较前后 DWG 位移和源图纸位移一致、裁切几何哈希不变。数值容差为 1e-6 mm。它是执行侧独立计算检查，不是外部第三方 CAD 认证。

```sh
.venv/bin/python scripts/audit_native_dwg_points.py \
  --net work/feature-composite-evidence/motor-after-net.json \
  --dwg work/feature-composite-evidence/motor-after.dwg \
  --previous-net work/feature-composite-evidence/motor-before-net.json \
  --previous-dwg work/feature-composite-evidence/motor-before.dwg \
  --point-id 实际持久点ID \
  --output work/fold-join-evidence-20261110/motor/native-audit-rerun
```

本轮已补充“方盒与圆柱均包覆”的命名模块样例：真实界面单次点击 Body 后，默认包含同组 Terminal，邻接 Unrelated-device 未选中，excluded_instances 为空。源文件 occurrence 命名已修正并经真实导入核对，生产选择规则仍拒绝将纯数字父组当成可靠设备组。旧 `cube-cylinder` 的排除开孔结果保留在旧附录。

## DWG 显示限制

原软件为 OpenCADStudio v2026.45。其反存 DXF 存在 owner=0 TABLESTYLE 缺陷；严格验证仅允许移除已诊断的 audit code 202 对应 TABLESTYLE 孤儿记录，保留原 DWG 和原始反存文件，其余异常不得忽略。实际 GUI 截图必须以 DWG 哈希、版本 ID 和 PNG 哈希绑定。全图小字需要局部放大；软件底部仍可能显示 CPU 渲染提示/命令栏，反向尺寸文字可能倒置。字体回读若缺失应判验收失败，不能仅凭截图可见当作全实体通过。

## 打包门禁与内容

`python scripts/package_feature_delivery.py --check` 只检查，不构建、不执行 npm pack、不创建输出目录或源码归档。检查要求本轮 `workflow.json` 与 `native-audit/native-dwg-audit.json` 均通过，同一个电机 STEP 哈希、前后 NetResult 和实际 DWG 哈希一一绑定，同一持久点确实移动、CUT 不变、恢复状态保留新位置。原生制造未满足项或片数约束未满足会阻止本轮打包。最终打包前必须先提交选定源码，归档使用 `git archive HEAD`；不得先归档再提交。

打包清单将原生出图/可编辑草稿流程通过与 complete_manufacturing_acceptance=not_completed 分开记录；允许工作草稿链路交付，不将复杂曲线接口待复核升级为完整制造通过。

新包包含插件 tgz、特征需求与完整源码、完整电机 STEP、新流程/原生 DWG 审计和明确选择的证据。旧 cube/cylinder/cube-cylinder 的已复核材料放入 `simple-v1-appendix`，与新验收分开保存。可用 `--supplemental-workflow` 明确加入本轮小组合或其他新流程；每份记录分别列出 UI 流程与原生审计是否已完成，不自动将补充流程升级为完整制造通过。可用 `--preview-report` 指定本轮最终 DWG 的原软件 PNG 绑定报告；不收集试用登录令牌、cookie 或私密服务状态。

整星 15 分钟目标已经暂停，不作为此次打包门禁。既有整星导入、几何显示和可选取性限制详见 `docs/reports/step-import-comparison.md` 与旧报告；不得据此宣称完整整星已可用或已通过。局部/有限样本的网格性能和面积比较不能扩大为整星性能结论。

## 本轮实际 DWG 与位移审计结果

- 完整 STEP SHA256：`c2e6357e02bfb57e27999bd595fbdc59b11c46bc8024e31e94ada9b22ab69c44`。
- 新工程 `de4f7f8e6ddc4545a3df829d51af58f1`：8 个基础体、23 个制造面，经 4 条平面折痕合片后为每层 19 个独立裁片。默认上限 10 时保留预览并禁止制造导出，明确提高到 30 后继续。
- 原生软件 OpenCADStudio 2026.45：前后 DWG 均为 DWG2018/AC1032，原生审计均为 0 错误、0 警告；严格源图纸全实体回读通过。
- 15 个圆形接口均生成分瓣舌片草案；数字几何无诊断，结果保持 `needs_review / generated_draft_needs_material_sample`。
- 实际 CUT 为 24 个 LWPOLYLINE；10 个位置标记 POINT、46 个可编辑 DIMENSION 保留；after 精确回读“电机组合包络裁片；单位毫米”。
- 持久点 `fp:auto:9b16f106362c0d99b947:feature-1-face-5:0` 的实际 DWG 位移为 `[11.130533148047789, 0.0]` mm，与源 DrawingDocument 完全一致；CUT 几何 SHA256 前后均为 `310bd256a44f6571be72f2693a897c4a152c92bd8db402b12290fe5d867e771e`。
- before DWG SHA256：`b7af48769f94660d4622ad9716164b5b1043c63c1da354a77559e53ea8dec465`；revision `ce4edbb0fcac453ebe7261171e3e7375`。
- after DWG SHA256：`c0683fc47c7de384e244ea6a1ac30d8a1f197511ec45ed4f601763bf1079f91a`；revision `743e03d8903d41ecb6b8f4c636e18298`。

最终审计文件为 `work/fold-join-evidence-20261110/motor/native-audit-rerun/native-dwg-audit.json`。

最终原软件 PNG 与未修改的原始 preview 报告来自同一次实际 UI 导出：`work/simple-v1-trial/data/published/5c3d212cb2624f909931d0b22cb06d9f/drawing-preview.png`、`drawing-preview.preview.json`。PNG SHA256 为 `b0438373f7515bcb51551be544a43d920db6d522f2f2113d7ba4390a0c71c8cc`。原报告记录的 staging 路径在发布时原子改名；包装以同一 published 目录的同名文件和相同哈希解析，保留报告原字节。原软件全图为 729×579，长条排样使文字较小；中文字符完整性由真实 TEXT 回读核对，不能将全图小字清晰度说成已提升。

## 本轮补充样例

下表均为本轮 `feature_composite_v1` 的实际 UI 导入、选择、原生展开和 DWG 导出结果。每例仅作一次单版本原生回读，不重复拖点，也不追加 GUI 截图。

| 样例 | 基础体 | 每层独立裁片 | 材料层/总片 | POINT | 可编辑DIMENSION | CUT多段线 | 原生审计 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 方盒+圆柱模块（两者包覆） | 2 | 3 | 1/3 | 10 | 16 | 4 | passed |
| 方盒 | 1 | 1 | 1/1 | 10 | 12 | 1 | passed |
| 圆柱 | 1 | 3 | 1/3 | 7 | 6 | 3 | passed |

各例实际 DWG 原生审计均为 0 错误、0 警告；标记独立坐标计算最大误差均为 0 mm（容差 1e-6 mm）。三例均无 TEXT，不将界面特征摘要当作图纸文字。证据分别在 `work/fold-join-evidence-20261110/{module-rerun,cube-rerun,cylinder-rerun}/` 的 `workflow.json` 与 `native-audit/native-dwg-audit.json`。

- module：STEP SHA256 `cebcad344a4b1474a895bfc75a233502b05d13a08454c35cae22b5845647d248`；实际 DWG SHA256 `0536caf698edeb26d92c5f474af97af029a2ed1d13e929da7b5ee5360974fab6`。
- cube：STEP SHA256 `d202191009d1e1f3081a2616b8c7cc7734b254d5de00270bdbdad6666c3c8f32`；实际 DWG SHA256 `bb6078bc6308da877e098243e6f82f0734b0702923ca4b37ff42eb9ca5e90278`。
- cylinder：STEP SHA256 `f902fe480af5faa9b2657f03c682071fb6c69806d5ba49cc9f112e3b3a122747`；实际 DWG SHA256 `094f2589c9208b1e14d36c1e45c64f3702bd25b7e52f79ae38eccd8991a2c3a1`。

这些样例验证本轮原生草稿链路与默认范围，完整制造验收仍为 not_completed；复杂接口、安装面开底/固定限制继续适用。

## 源码回归检查

冻结构造版本为 `native-serial-feature-union-v1`：使用串行原生 Fuse，解决受限 worker 中并行 Boolean 线程池死锁；旧开发版面序不迁移，本轮最终验收必须来自冻结版本新建工程。

本轮最终回归为：`tests/blanket` 209 passed；特征/发布定向 11 passed；contracts/formats 204 passed、2 skipped；前端 TypeScript 检查和插件构建通过。上述检查有重叠，不加总为一个通过数量；跳过项不计为通过。这些源码回归不能代替真实电机 DWG 与拖点验收。

最终检查日志随包收录：`blanket-regression.log`、`contracts-formats.log`、`feature-focused.log`、`frontend-build.log`。

本轮原软件预览清理修复后，`tests/formats/test_opencadstudio.py` 在真实 OpenCADStudio 上为 14 passed（24.54 秒）：覆盖 DWG 原生重开、Unicode、实际 GUI PNG 绑定、预览不可用时保留 DWG，以及拒绝 TERM 的私有子进程清理。预览私有 profile 已移出工件发布目录，退出时等待 GUI 子进程；完整发布 manifest 检查继续严格执行。

完整发布 manifest 守卫定向检查为 1 passed（3.09 秒）：允许合法 nested/result.json 参与 lease 验证，仍拒绝未列入清单的晚到文件。此检查验证目录边界，不放松完整清单要求。


工程保存/恢复后同一位置标记与中文注释均保留。恢复会生成新修订；它不冒充已导出 after DWG 的 `743e03d8903d41ecb6b8f4c636e18298` 修订。
