# B10 规则罩形（2026-11-08）

本批提供后端规则几何与可继续编辑的工程状态；不包含 B11 展开搭接或 B12 交互。仅一个外壳为安装轴对齐六面矩形盒的实体 occurrence；实体可有封闭内部空腔，分母始终取外形盒。曲面、斜切盒、任意多实体组合和其他非规则包络明确返回 unsupported_B13，不静默套世界 AABB。

## 输入与操作

`blanket.generate` 使用已保存 revision.parameters 中的 BlanketInput，model_ref 必须一致，target_instances 只接受当前 B02 mesh-map 的物理 occurrence。安装 frame 为 mm、右手正交 XYZ，z=0 必须是设备底平面；x/y 原点可不在设备中心，锚点由设备底面中心确定。源 BRep 与位姿只读，局部变换和布尔计算对 deep copy 执行。

默认 allowance 为 linear_xyz / [1.05,1.05,1.05] / installation_bottom_center。可选 `dimensions_mm:[L,W,H]` 覆盖三个独立尺寸，正有限数且每项 >1e-6、≤1e7 mm；该限制是实现数值范围。100mm设备得到105mm内尺寸，侧2.5、顶5、底0。缩小尺寸不会增大分母，仍须通过覆盖及穿入检查。

`blanket.edit_shape.parameters={result_id,baseline_id,dimensions_mm?,openings?}`，两项修改至少有一项。必须指向当前 revision 的成功结果及精确 baseline_id；先创建不可变候选 revision，只有检查通过且 publication CAS 仍当前才切换 head。失败/取消不发布半成品，旧成功结果仍可用；晚到成功只入历史。直接修改 revision 后旧结果不可当当前读取或保存，重新 generate 才可保存。

`GET /projects/{id}/blanket-result` 只对 blanket 身份返回当前 revision 的 `{result_id,blanket,artifact}`，尚未生成返回 null；保持 owner/session/module 授权。重计算在现有独立 worker 内，不在 HTTP 线程导入 OCP。

## 基准与几何

EnvelopeBaseline.id 对 model_ref、target_instances、installation_frame、envelope_policy、rule_version 和选中源形体 hash 做规范 SHA256。源对象或 frame 变化生成新 baseline；尺寸、开口与面覆盖选择改变不扩大分母。同一 identity 的历史 baseline 必须与从原始源模型重建出的参数、算法、体积完全匹配；修改分母被拒绝。source_revision/confirmed_revision 保留首次创建版本，这里表示技术选择绑定，不是人工制造批准。

制造输出为 `manufacturing.brep` 和各 `panels/<side>.brep`，正常五面、无底。Panel 为候选，带同 revision ID、精确源 FaceRef、世界 mm frame 和实际 UV 外环/孔；没有伪造展开。每个平面 mapping_ref 仅描述该 Panel 的 UV。

开口为 `{id,panel,loop}`，panel 为 x-/x+/y-/y+/z+；loop 是当前派生 Panel frame 的 mm 多边形。必须简单、正面积、严格位于单片内部且与其他孔不相交/相切；不是源设备 UV，也不按比例随尺寸缩放。用户改变尺寸使孔越界则失败。excluded_faces 可排除整块真实设备外表面，included_faces 非空时只保留所列覆盖面；排除的整片成为评价封口，不能再向其添加局部孔。空制造罩拒绝。默认无需 included_faces，五面全包。

每个底面/开口/排除片有独立 `closures/*.brep` 及 evaluation_only=true 记录。对制造面与这些封口实际 Sewing 后形成独立有效单闭合 Solid `evaluation.brep`，不对开口壳调用 Volume。`baseline.brep` 是独立固定外形盒。两闭体实际体积比在 [1,1.2] 内可通过单项；端点仅吸收32 ULP浮点误差，非制造容差。另对源实体减评价闭体检查覆盖，并独立检查外形盒三个方向包含性（仅64 ULP坐标舍入量），防止原生布尔将微小穿出视作重合；实际制造片体与源实体 Common/内侧分类独立检查穿入。布尔使用 non-destructive、serial OCCT，避免受限 worker 内并行池在贴合 STEP 面时阻塞。有效正尺寸矩形构造及严格孔域保证无折回/自交，不承诺任意输入曲面的此项检查。

数值设置：安装/边界判定1e-6mm、sewing1e-7mm、覆盖外部体积≤1e-6mm³、穿入面积≤1e-8mm²；面交区内部分类沿法向±1e-5mm、分类公差1e-7mm。以上是解析规则算法数值设置，不是工程师确认的制造公差。测试oracle长度1e-6mm、体积相对1e-6，边界比例另用实际原生体积和ULP策略。

`cover.glb` 由真实制造片体网格生成，CadQuery输出已为Y-up，再归一到米，与B02显示坐标约定一致。node.extras.panel_id绑定Panel；GLB仅显示，BRep/参数才是工程真值。开口封口不进入显示模型。

## 保存、恢复与下游

EngineeringBundle rebuilder_version=b10-state-v1 保存当前 BlanketResult、baseline、构造参数、版本链，以及源与派生资产引用。同工程/同模块恢复核验全部资产bytes/hash；从原始BRep重建罩形和检查，创建新revision，重绑定Panel ID，保持baseline元数据和分母。缺失/损坏引用、算法或分母篡改拒绝，旧head不变。b06/b09历史工程仍可读取。该包是受控数据根内引用式工程，不是单JSON离线迁移包。

downstream 记录 revision_id、checks_revision、panels=candidates、unfolding=not_computed。B11必须消费新版本原生面/孔/开口边及独立评价封口，不能把封口制成布片；罩形更新后不得沿用旧裁片、检查或mapping。B12才实现交互。

## 验证门槛

`verify_batch.py B10` 是本批可执行的完整规则算法验收，登记所有B10测试、真实HTTP重启恢复、原生读回、Three加载、B02/B06/B09消费审计、既有几何/服务/喷漆回归及旧项目边界。仅B10精确规则 `B10-consumes-B09-development-v1` 可消费B09独立批准的开发记录；没有通用blocked前置忽略。核对受测祖先源码指纹、134项开发产物、独立证据hash、12条命令和最新退出码回执。三份运行后更新的archive/exit元数据，其旧hash按开发起点提交核对，最新回执另绑实际development/summary哈希；原记录不改写。

`verify_batch.py B09` 仍实际exit2/blocked；B04 AutoCAD、B05原生ASM/PRT、B07正式DSH和工程真值批准缺口保留。B10本批验收通过与独立审查是不同事实，独立审查由调度器安排。
