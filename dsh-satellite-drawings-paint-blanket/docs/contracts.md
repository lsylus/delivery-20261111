# 公共接口与数据契约

本文件是新系统的设计契约（v1），不是现有已发布接口。B01建立Schema和契约夹具；后续批次必须补充新增字段及迁移规则，同时修改生产代码、测试和消费者。所有新增名称以本文件为准，旧ZIP模板中的null、template_only和相反默认说明由最新决定覆盖，模板本身作为只读来源保存。

## C01 身份、版本与几何引用
- `Project{id,owner_id,name,module_states:{paint,blanket},created_at}`。两业务数据空间独立，显式授权后共用同一model资产；不能凭同名跨工程引用。
- `SourceManifest{schema_version:1,asset_id,main_file,files:[{relative_path,sha256,bytes}],assembly_digest,detected_format,vendor,vendor_version,units,load_status,missing_refs,conversion_evidence}`。digest按相对路径排序的完整清单计算，不仅hash主文件；保留Creo `.prt.5/.asm.5`，不要批量删版本后缀。
- `ModelRef{project_id,model_id,model_revision,assembly_digest}`；`EntityRef{...ModelRef,instance_id,entity_kind,entity_id,signature}`。definition与occurrence分离；重复实例必须有不同instance_id和world_transform。
- 所有工程长度mm、角度rad；转换单位明确记录。局部坐标系为原点和正交XYZ轴（右手系）；刚体变换以明确行列约定的4×4矩阵保存，B01约定行优先、列向量作用。镜像/非刚体不能悄悄按刚体处理。
- `FaceRef`只在当前model_revision内稳定；签名含类型/面积/重心/法向/邻接，跨revision匹配歧义返回needs_reselection。GLB triangle索引只能经当次mesh-map定位FaceRef，不是持久工程ID。
- `EngineeringRevision{id,parent_id,model_ref,parameters,selection,overrides,document_edits,input_fingerprint}`不可变。参数/选择/几何修改新建revision；纯相机改变不建revision。undo/redo切换可追溯版本，不复用已删除对象ID。

## C02 作业、发布与错误
- `Run{id,project_id,module,operation,input_revision,input_fingerprint,idempotency_key,state,progress,worker,tool_versions,artifacts,checks,error}`。
- state：queued → running → succeeded/failed；运行中取消先cancel_requested，执行端结束后cancelled。取消与发布冲突以事务/租约检查解决。stale是结果与当前revision的关系，不冒充worker失败。
- 相同owner/project/operation/input/idempotency_key只创建一个run；不同输入同key返回409。发布前比较当前revision与fingerprint，晚到结果只入历史。
- error：`{code,message,stage,retryable,evidence_refs}`。401无认证，403无权，404不存在/不可见，409版本冲突，422输入不合法，503能力未配置；异步算法失败在run中记录。
- OCP重计算在独立进程/worker，不在HTTP请求线程做大模型运算。设置可配置超时/内存/并发（首版默认1），进程组取消与恢复清理必须测试。
- worker先写run临时目录，完整性校验后原子登记；失败/取消半成品不进入正式产物列表。服务重启恢复任务状态，不能让running永久挂起。

## C03 检查、复核与产物
- `Check{id,status:pass|fail|needs_review|not_run|not_applicable,scope_refs,observed,limit,units,algorithm_version,evidence_refs,reason}`；不适用必须有理由。
- `Review{reviewer,revision_id,result_id,decision,reason,at}`与作业状态分离，成功不自动批准。
- `Artifact{id,run_id,revision_id,role,format,mime_type,sha256,bytes,relative_storage_path,validation}`。HTTP返回受控下载URL而非服务器任意路径。
- 预览允许标记未复核；正式出图必须关联检查和人工复核状态。fail/needs_review不冒充合格制造文件；未解决问题的导出若提供，必须明确draft并含诊断。
- `EngineeringBundle`保存源manifest引用、派生B-rep/罩形构造参数、裁切/接缝/点、DrawingDocument、版本与重建器版本。必须支持插件中重开修改保存；STEP/GLB仅为辅助产物。

## C04 几何库中立契约
- 模块 `geometry_core.{xcaf,bounds,transforms,topology,serialization,solid_pairs}`不依赖旧backend、账号、HTTP、业务ID或数据库。
- `read_xcaf_source(path,options)`保留源树、名字、definition/occurrence、本地/世界变换和document生命周期，B02用adapter输出ModelSnapshot；不能强塞旧CAD/geometry选择策略。
- `intersect_face_patches(left_face,right_face,*,fuzzy_tolerance_mm=1e-7,minimum_patch_area_mm2=1e-7)`返回 `{completed:bool,patches:tuple[cq.Shape,...]}`。None fuzzy原语行为保留；失败返回completed=false，成功无区域返回true+空tuple。不携带TC-/patch业务ID。
- measurement返回距离、交体积、面积等事实及完成状态，业务阈值在paint/blanket层；bounds策略区分保守与精确。分离近接触面不能只靠Common得到保护脚印。
- 原生TopoDS/cq对象只在worker内流转，跨进程/HTTP使用资产引用或序列化数据，不能传Python对象pickle给浏览器。

## C05 二维图纸与DWG
`DrawingDocument{schema_version:1,id,revision_id,units:"mm",frame,layers,entities,source_links}`：
- entity共同字段 `id,kind,layer,source_refs`，kind支持line/arc/circle/polyline/hatch/text/dimension/point；closed、内孔、曲线方向、HATCH外内环明确表达。
- 图层初始设计：OUTLINE、PROTECTION、CUT、FOLD、OVERLAP、FIXING、DIMENSION、TEXT；颜色/线型由drawing profile控制，不能靠截图画出假阴影。
- 预览SVG和DXF均由同一DrawingDocument生成；位置标注编辑进入document_edits，同版进入DWG。原生DWG转换保留可编辑实体，不能整图栅格化。
- `DrawingExporter.write_dxf(document,destination)`；`DwgConverter.capabilities()/convert(dxf,destination,profile)`返回ConversionEvidence；最终目标DWG版本由B04记录及重开验证，不把AC1032签名当已兼容。
- Converter证据包含工具版本、许可部署条件、输入输出hash、进程退出码、真实解析/重开记录、实体类型计数和尺寸核对。用同转换器回DXF仅辅助，不能替代AutoCAD独立重开验证。
- text中文、孔环、阴影、折线、搭接、点、尺寸均包含在最小样图中；DXF不是最终DWG交付。

## C06 原生输入
`NativeConverter.probe(manifest)->Capability`；`convert(manifest,workdir)->{step_asset,dependency_report,evidence}`。
Capability记录vendor/版本范围、OS、工具、可用/缺失/未验证、license_state、真实验证case_ids。输入按文件头和来源判别，不只后缀；未知格式明确拒绝。
允许Linux商业SDK或远程有许可CAD worker；服务端使用登记操作和资产相对路径，不执行客户端任意shell。源数据不上传公共转换站。资源/许可隔离，超时取消，输出目录独立；检查路径穿越与压缩包解压越界。
缺件或只部分导入不能声明完整成功。外部引用、抑制部件、轻量化表示的处理记录在manifest中。STEP对照不能代替原生装配加载完整性的证据。

## C07 喷漆
`PaintInput{model_ref,target_face_refs,scope_boundary,contact_threshold_mm:0.1,contact_comparison:"lt",contact_offset_mm:3,hole_offset_mm:3,boss_rule:"protect",boss_additional_offset_mm:0,rib_rule:"retain_paint",overrides,rule_version}`。
boss_additional_offset_mm=0是“不自动额外外扩”的产品实现，不代表用户已给出所有特殊凸台工艺。特殊处理可显式覆盖并保留来源。
`PaintRegion{id,kind:contact|hole|boss|manual,source_refs,local_frame,loops,protected,origin,confidence,check_refs}`。接触区域保留双方引用与每连通域证据；孔内部非材料域不能作为阴影填充。
阈值附近数值不确定区标needs_review，不偷偷将严格小于改为小于等于。穿透单列fail/needs_review，不解释为普通贴合。
平面孔采用目标面实际开口环，沉孔按目标表面的实际口部边界；盲孔等分类不确定由人工覆盖。方法及适用范围必须在B08结果中可见。

## C08 多层罩形、包络与展开
`BlanketInput{model_ref,target_instances,included_faces,excluded_faces,openings,installation_frame,allowance:{mode:"linear_xyz",factors:[1.05,1.05,1.05],anchor:"installation_bottom_center"},envelope_policy,cut_edges,fold_edges,unfold_base_panel,overlaps,fixed_points,rule_version}`。
规则方盒基准为安装坐标系中的已确认设备外形盒（不是全局AABB或内部材料体积和）；保持安装底平面，x/y对称放大，z仅向上。任意方向box需先构造安装frame。
`EnvelopeBaseline{id,source_revision,algorithm,parameters,closed_shape_ref,volume_mm3,openings_closure,confirmed_revision}`；派生罩形独立存储。B13复杂外形记录算法、包含性和封口，不能通过增大分母绕过1.2。
`Panel{id,surface_ref,outer_loop,holes,frame,source_refs,mapping_ref}`；`Seam{id,edge_a,edge_b,pair_orientation,kind:cut|fold|join,overlap_owner_panel,width_mm:15}`，折叠边不自动加搭接。
`FixedPoint{id,panel_id,uv_mm,position3d,mapping_ref,status}`；UV为裁片实际坐标，不是矩形0~1归一化；点在有效域中，不落入孔/裁片外。无强制数量默认，不编造材料边距；输入间距必须为正。
展开输出每裁片独立2D域、边邻接、正反方向和piecewise mapping；复杂曲面不能用单一平面矩阵冒充全域映射。裁切改变时点重新映射，歧义失效。
体积对计算副本封闭所有评价开口，罩内空间不含搭接重复用布。开口封口策略和包含性报告可复现。比例合格仍必须检查自交、穿入、覆盖和折回。

## C09 API及会话
新服务API根 `/api/v1`：
| 方法 路径 | 请求/结果及权限 |
|---|---|
| GET /health、/capabilities | 服务状态/格式工具能力；不暴露密钥 |
| POST /projects；GET /projects/{id} | 创建/读取授权工程；模块paint或blanket |
| POST /projects/{id}/assets | 上传文件或受控包，返回资产与manifest；禁止任意本机路径读取 |
| POST /projects/{id}/imports | asset_id/main_file/格式选项，202返回run_id；STEP先由B06，原生由B14接入 |
| GET /projects/{id}/models/{model_id} | 当前ModelSnapshot/树/网格资产映射及revision |
| POST /projects/{id}/revisions | expected_revision+selection/parameters，409拒绝旧版写入 |
| POST /projects/{id}/operations | OperationEnvelope，202返回run_id |
| GET /runs/{id}；POST /runs/{id}/cancel | 授权读取/取消，遵循C02 |
| GET /artifacts/{id} | 验证owner/project访问，流式下载 |
| GET/PUT /sessions/{id}/binding | 当前宿主session/module/project；跨session不能猜ID写入 |

`OperationEnvelope{schema_version:1,module,operation,project_id,model_ref,expected_revision,selection_refs,parameters,overrides,idempotency_key}`。
operation白名单：paint.generate / paint.edit_regions / blanket.generate / blanket.edit_shape / blanket.unfold / blanket.edit_seams / blanket.edit_fixed_points / drawing.edit_annotation / drawing.export / engineering.save / engineering.restore / history.undo / history.redo。B01定义schema，业务批实现对应操作；未实现返回明确能力不可用，不假成功。

宿主代理路径 `/api/satellite-paint/service/*`、`/api/satellite-blanket/service/*` 映射共用后端/api/v1。服务端校验可信宿主身份与工程授权；浏览器不带后台静态token，任意X-Owner头不可自认身份。CORS不是认证。
MCP工具包装同一API与operation白名单，不直写数据库。两插件namespace分开，重型作业返回run_id后查询，不能提前报告成功。

## C10 视图和聊天
`SelectionContext{session_id,module,project_id,model_ref,engineering_revision,result_id,entity_refs,view:"3d"|"2d",local_coordinates,annotation,view_transform}`。
postMessage检查origin、source、session、消息白名单；切会话/模型/版本旧选择失效。可附截图，但必须有工程引用；圈选仅显示命中对象列表，不默认穿透隐藏面。目标歧义仅询问必要信息。
聊天、按钮和参数面板调用相同业务command；同revision返回统一三维/二维更新。保存“未提交草稿”和“旧结果过期”两个状态；UI不能重新调用demo绘图覆盖live结果。

## C11 案例与运行配置

B01建立并用Schema验证以下文件结构，业务批补齐实际值。配置中路径是本机运行路径，不在聊天中隐式传递；密钥使用环境变量名或受控凭据引用。

- `CaseManifest{schema_version:1,cases:[{id,module,purpose,split:development|holdout,source_manifest,main_file,vendor,version,expected_instances,reference_artifacts,revision_match_status,selection_spec,expected_checks,tolerances,requires_tools}]}`。未确认字段为null并有原因，不能用0/空数组伪装已验证。selection_spec在首次注册时可为可复现的名称/位姿定位条件，打开后固化本次FaceRef及签名；跨修订验证必须重新定位。
- `work/config/converters.local.json`：`{dwg:{adapter,executable,target_version,font_paths,timeout_s,license_ref},native:{adapter,endpoint_or_executable,vendors,timeout_s,credential_ref},work_root}`；B04/B05分别填各自节，不互相覆盖。对应脱敏example提交，local文件不入Git。
- `work/config/acceptance.local.json`：`{service_url,credential_ref,case_root,timeout_s,memory_limit_mb,concurrency:1,cad_reopen_evidence_root}`。性能预算由开发方按实测环境设置并记录，不等于用户SLA；设置不能为了通过而跳过大样本。
- `work/config/release.local.json`和`host-test.local.json`登记新服务数据根、选定空闲端口、镜像/包路径、宿主测试profile、只引用的凭据；禁止用旧工程数据根。B15生成前检查路径及服务归属。
- `summary.json`：`{schema_version:1,batch_id,status,code_revision,dirty,prerequisites,commands:[{argv,exit_code,log_ref}],tests:{required,passed,failed,skipped_required},inputs,artifacts,checks,manual_evidence,limitations,resources_created,resources_cleaned}`。status=passed须有真实测试且skipped_required=0，所有必需checks通过、人工证据齐全。registry精确列出各批必须的测试路径/证据，不按“报告文件存在”放行。


## B01 可执行契约补充（2026-11-06）

设计已映射到contracts下JSON Schema 2020-12与OpenAPI3.1；不是生产API发布。新增cases/config/summary三个Schema以落实C11。对象默认禁止未知字段，未来添加可选字段仍须更新Schema/生产者/消费者；schema default是文档元数据，不会自动注入输入，旧template_only内容不能覆盖当前默认。

ModelRef.model_revision为从1开始的整数；EngineeringRevision.id、expected_revision为不透明非空字符串。Run.progress为0～1，state不含stale；取消/失败/运行中的Run不得列正式artifacts。事务及版本冲突真实行为由B06实现，B01只验证契约。操作参数中paint.generate与blanket.generate按各自输入Schema验证；其他操作的具体参数随所属业务批次收紧，未实现不得返回成功。

行优先、列向量的4×4矩阵，frame右手正交；scripts/contracts.py拒绝非有限数、镜像/缩放、跨模型/修订引用与非法source digest。source digest按docs/decisions/numerical-policy.md的规范序列化计算。跨revision几何重匹配、装配world transform组合、真实裁片有效域仍须B02/B06/B11验收，不能由结构校验代替。

DrawingDocument实体采用按kind区分的封闭结构，明确圆弧rad角、方向、polyline.closed以及hatch外环/孔环；B04接入导出器时需扩充真实格式所需属性并回归消费者。Seam只有一个overlap_owner_panel；fold的width_mm=0且owner=null，其他接缝需要owner；默认15mm可逐缝覆盖。

CaseManifest.source_manifest指向B01库存清单，库存标识inventory_not_loaded_assembly/zip_inventory_not_loaded_CAD，不是已导入资产的SourceManifest。缺真值字段null必须有逐字段原因，expected_instances禁止0。完整性、厂商版本支持、真实工具许可当前未核验。summary由统一runner产生，passed要求实际测试、零skip、所有登记检查和证据；无登记Batch不会生成默认通过。

## B04 可执行出图补充（2026-11-06）

C05 v1 字段保持不变；运行包携带 drawing.schema.json，与根契约逐字节回归。DrawingDocument 拒绝空出图、非有限数、重复 ID、错误环方向及无效孔拓扑。二维实体使用 frame 中局部 mm 坐标；DXF 保留 frame/revision/id 元数据。

B04 profile 固定 R2018→ACAD2018、DroidSansFallbackFull.ttf，当前只验证解析样图。尺寸实体是原生可编辑旋转线性 DIMENSION，按端点方向对齐；position 定义尺寸线偏移。支持 CONTINUOUS/DASHED/CENTER、SOLID/ANSI31，其他未实现值明确拒绝。完整限制见 architecture/dwg-output.md，不扩大为所有 DXF/DWG 兼容声明。

DwgConverter 的可用性、一次真实转换成功、AutoCAD 重开编辑批准分别记录。convert 返回 needs_review 草稿和真实命令/退出码、工具与输入输出 SHA-256、反向实体检查；不会自动注册正式 Artifact。license_ref 可以指向本批明确授权的 b04_local_evaluation 记录，但该记录不授权生产部署或再分发。

AutoCAD 人工证据绑定确切 DWG bytes/hash、revision、软件版本、编辑后文件及操作截图/日志；只用 ODA 回 DXF 不满足此项。统一 runner 对已审阅产物验证原 bytes，避免重新生成时间戳使审阅错绑；输入/源码变化使审阅过期。前置 Batch 源码 hash 对其原验收提交核验，归档运行证据仍核实保留文件，绝不改写原 summary。

## B02 可执行几何补充（2026-11-07）

C01的ModelSnapshot及common/model Schema保持B01 v1不变。geometry_core公开load_model_snapshot与tessellate_with_face_map；详细调用、world-mm到glTF米/Y-up约定、BRep资产、失败与发布边界见architecture/geometry-core.md。新增mesh-map.schema.json v1，FaceRef使用EntityRef且限定entity_kind=face；每primitive绑定当前ModelRef和精确GLB SHA256。变换输出显式layout=row_major、action=column_vector。不同revision/GLB或越界拾取返回needs_reselection；不能将原生Python对象跨HTTP传递。


## B03 可执行测量补充（2026-11-07）

C04 face 原语的默认 `fuzzy_tolerance_mm=1e-7`、`minimum_patch_area_mm2=1e-7` 及 None fuzzy 保持；面积严格大于门槛才输出。原有 completed/patches 不变，新增可选 failure_stage/failure_message 供 worker 诊断。参数错误抛 ValueError，原生失败返回 false+空；成功空与未完成不同。

`geometry_core.solid_pairs.measure_shape_pair(left,right,*,intersection_distance_limit_mm,zero_volume_tolerance_mm3,fuzzy_tolerance_mm=1e-7,minimum_contact_area_mm2=1e-7,maximum_planar_face_pairs=100000)` 返回 SolidPairMeasurement：distance_mm、intersection_volume_mm3、contact_area_mm2、left_valid/right_valid、intersection_performed、completed=true、contact_scope。有效性与完成独立；消费者必须自行检查有效性及工程规则，不能只凭 completed 批准。距离大于显式搜索门槛时可得零交体积，intersection_performed=false 明确未运行 Common。area=None 表示未知/没有取得正面积，不是已证明零面积。

`measure_planar_contact_area` 返回 PlanarContactMeasurement（新库的结构化结果，不是来源 float|None）：completed、area_mm2、scope=planar_faces、nonplanar_face_count、failure_stage/message。成功仅覆盖平面候选对；不证明曲面接触面积。无正面积用 None；预算/任何候选失败用 false+None，不发布部分面积。整个 measure_shape_pair 遇未完成则抛 SolidPairMeasurementError，completed=false，stage 为 input_validity/distance/intersection/planar_contact/face_intersection/planar_budget；异常不填0。错误字符串不作为业务API。

Common 采用非破坏构造，不改输入 BRep。默认1e-7是内核数值参数；0.1mm业务距离与3mm保护策略不在本库。重复实例必须传入各自 world shape；包络与源实体是不同输入，不能互换证明干涉。只在受控worker内传 cq/TopoDS 对象；B06处理隔离/超时/取消，B08负责近接触方向和覆盖，不由 Common 空推断没有保护脚印。common/model/mesh-map JSON Schema v1 不变，本次数据类型仅是进程内 C04 契约。


## B06 可执行工程服务补充（2026-11-07）

C01/C02/C03/C09的隔离dev API已经实现，正式宿主身份未配置。完整协议与恢复语义见architecture/project-runtime.md。API根/api/v1；每个请求需要operator预置的随机dev bearer，并校验loopback真实peer/Host、拒绝Origin。用户/模块/session只来自服务端credential映射；客户端owner_id和任意X-Owner不构成授权。未配置的正式host模式拒绝启动。

新增runtime.schema.json v1登记CreateProject、ImportRequest、RevisionRequest和OperationEnvelope/SessionBinding引用。ImportRequest必须带expected_revision、idempotency_key，format_options只支持空对象；初始null head的请求值为`empty`。RevisionRequest显式带model_ref以支持同工程两模块共享源模型，selection仅接受当前mesh-map精确FaceRef。参数、selection、overrides、document_edits变更新建不可变revision，旧expected返回409。

Run v1的operation枚举新增model.import（通过imports路由），OperationEnvelope业务枚举不变；engineering.save只接受空parameters，engineering.restore只接受{artifact_id}。其它未实现操作503。Artifact v1增加可选download_url，指向/api/v1/artifacts/{id}，相对存储路径不是任意本机路径读取授权。EngineeringBundle v1允许drawing_document=null，表示B06尚无二维业务图，不伪造空图；已有非null DrawingDocument契约不变。生产包携带与根contracts逐字节一致的schema，消费者和契约测试已回归。

POST /projects返回201 Project；原始STEP上传为application/step或application/octet-stream加X-Filename，返回201 {id,filename,sha256,bytes,format}，不接multipart或ZIP。GET /projects/{id}/assets/{asset_id}增加授权源文件下载；GET /projects/{id}/revisions/{revision_id}增加同模块历史revision读取；GET models返回{snapshot,artifacts}包装以提供源BRep/GLB/mesh-map下载引用。GET capabilities明确stage=B06、dev-only、host not_configured、格式和操作能力。所有路径均验证owner，写入需要session绑定，业务产物跨模块拒绝；源模型产物在同工程可共享。

SQLite/WAL事务持久化工程、绑定、版本、幂等key及run租约。worker使用B02独立进程，临时产物完整校验后原子发布；取消是cancel_requested到执行端确认后cancelled，重启后running变明确失败、queued继续，旧版结果只入历史。检查通过不等于制造批准。源STEP/BRep是几何真值，GLB仅显示，B04 blocked/FAIL及最终AutoCAD门槛保持。


## B08 平面喷漆实现（2026-11-07）

新增PaintResult v1：revision_id/model_ref/status、regions、diagnostics、C03 checks、DrawingDocument、由相同region loops生成的world-mm overlay、projection/feature evidence、numerical_policy与algorithm_version。status为passed/needs_review/failed，作业成功不代表制造批准。PaintRegion新增可选area_mm2、contributor_kinds、provenance；混合来源的兼容kind为manual，origin仍独立记录computed/manual。

PaintInput.overrides从开放object收紧为PaintOverride{id,version,model_revision,face_ref,classification:contact|boss|rib|exclude|unknown,reason}，空列表兼容。只按精确当前FaceRef绑定，重复/失效/未应用覆盖返回needs_review，不做自动跨修订重绑。整体非标准特征按cap面分类，分离安装特征按实际贴合面分类。

paint.generate已在B06受控worker实现。操作parameters必须等于已保存revision.parameters，target_face_refs等于selection，overrides完全一致，否则409；原先权限、幂等、取消、租约、原子发布不变。只支持同向共面选择；非平面/多平面、预算耗尽、分类或局部间距未知不能空pass。C04库接口不变，0.1mm业务门槛与1e-7mm核fuzzy分离。

结果资产paint-result.json包含完整检查与overlay，drawing.json必须等于内嵌DrawingDocument。passed可成为当前结果；needs_review仅为历史draft；failed记录具体paint checks但不登记正式资产，旧完整run仍可读取。Capabilities implementation_stage新增B08枚举，公开paint.generate；paint.edit_regions、DWG及真实宿主仍不可用。source_links、孔环、来源与同revision一致性由真实HTTP和解析几何验收；详见architecture/paint-rules.md。

孔取真实开口环并裁剪到有效材料；标准整体圆形凸台保护自身cap并保留高度，不默认扩3mm；非标准筋/凸台显式分类。默认pair/points/时间预算10000/500000/60s，弦差1e-7mm、offset每象限2048段，仅作为数值实现设置。B04仍blocked/独立FAIL，最终AutoCAD打开、编辑、保存、重开要求保留。

B08生成区域和图纸实体ID含engineering revision，旧修订的区域ID不在新修订复用；三维/二维引用仍由同一PaintResult绑定。


## B08 独立审查修复 R1

阈值不确定区改为直接比较外向舍入的端点 threshold±(1e-7mm+local deviation)，另外用8 ULP处理浮点运算边界；业务严格lt不变。粗筛覆盖所有允许的local deviation，不先丢弃上侧边界。

通孔需要源实体反向面上的真实内环出口，并以该出口沿法向到目标面的实体柱与源BRep做Common，确认材料交体积≤1e-9mm³。嵌套出口可证明已知通的台阶/沉孔，保护仍取被选表面的口部。盲孔/背面不通凹袋或缺少该证明时needs_review；只有与整个口部匹配的单一底面FaceRef可通过有版本/理由的hole或exclude覆盖明确处理，不接受目标大面的笼统覆盖。PaintOverride.classification增加hole枚举，针对上述显式口部保护策略。

PaintOverride.id在整个数组内唯一：Schema声明uniqueItems和项目扩展x-uniqueBy:id，契约脚本与生产验证器均注册扩展并在跨Schema引用中执行；原生标准JSON Schema的uniqueItems仅比较整个对象，不能表达按任意属性唯一，因此消费者必须使用该项目验证器语义，不能忽略扩展。算法入口独立检查ID唯一；应用状态比较完整的规范化覆盖记录，不以ID set替代。

B08全局pair预算在每次委托B03前预留全部len(left.Faces())×len(right.Faces())面对上界及本地pair；各occurrence、各目标共用同一预算，超限在调用前停止且丢弃部分结果。B03接口保持不变、不提供消费回调，因此预留不因提前退出而退还；这是保守计费而非精确计时/SLA。普通孔的实体柱证明另外计入本地pair。B03/B06原始Schema和几何接口不变。

R1生成结果algorithm_version为b08-planar-v1-r1；Schema兼容读取旧b08-planar-v1历史结果，rule_version仍为paint-v1。


## B07 工作台与隔离宿主桥

C01/C09/C10 的 ModelRef、FaceRef、DrawingDocument、OperationEnvelope Schema 不变。两个插件各自 workspace/MCP/代理前缀，打包包含共享代码。live 仅读取真实 B06 API，GLB与mesh-map必须hash和ModelRef匹配；二维为明确标记的选择映射fixture。owner/session/project/module隔离草稿，旧revision不恢复；视角不新建revision。聊天来源/当前服务端绑定与revision每次复核，只写草稿，切session解绑并取消异步旧引用。详情与可复验命令见 architecture/workbench-host.md。

本批只配置隔离宿主适配，正式issuer/audience/签名/key discovery/subject映射/session撤销协议未配置，因此B07总体blocked，不以隔离验收冒充正式接通。MCP隔离operator配置只在服务端私有0600文件，工程保存真实调用B06；业务不可用保持503。B04 blocked/FAIL及最终AutoCAD打开、编辑、保存、重开要求不变。

## B05 原生输入预检（blocked）

C01 SourceManifest 和 C06 既有公共 Schema 不变。新增 CLI wrapper 的 source_manifest 遵循 C01；dependency_report/geometry 单独保存未验证信息，不把名称线索当原厂实际加载结果。load_status=not_opened、units/missing_refs/conversion_evidence=null；完整 files 清单排序后的紧凑 UTF-8 JSON（sort_keys）计算 assembly_digest。

NativeConverter 当前没有已授权、已选型的 operational adapter；probe 返回 blocked/available=false，convert 核验副本后抛 NativeConversionUnavailable，不产生 STEP 或发布模型。现有 converters.local.json 只读取 native 段，其他配置不变，禁止任意执行命令。B02 读回返回 readback_only，不代表原生等价。将来原厂实际依赖、抑制/轻量/族表、实例层级/位姿、单位、体积/边界及容差对照全部满足后才能放行。B14 集成前须补实际 adapter 并重新验收，不更改当前 STEP API。详见 architecture/native-input.md。


## B09 STEP 编辑及 DWG 草稿（隔离开发范围）

`GET /projects/{id}/paint-result` 返回当前 revision 对应 `{result_id,paint,artifact}` 或 null，不返回旧版结果冒充当前。无图的 needs_review 结果保留 diagnostics，但不能编辑或导出。B09 Capabilities 增加 stage=B09；配置转换器才列出 drawing.export。正式 DSH 身份仍未配置。

`paint.edit_regions.parameters`：`{result_id,action:add|exclude,points:[[u,v],...],reason}`，或 `{result_id,action:move,region_id,delta_mm:[du,dv],reason}`。有限 mm 坐标、3..512 顶点、简单正面积多边形；服务器解析当前结果精确区域 ID。移动只支持被选图纸平面的保护区，其他平面明确拒绝。增加/排除均裁剪真实材料及孔；移动持久化原边界和位移。跨模型/目标面的覆盖不可静默重绑。

`drawing.edit_annotation.parameters={result_id,annotation_id,text,position:[u,v]}`。同 ID 可移动或修改单行文字，只改变图纸及工程 revision，不改三维保护几何。`drawing.export.parameters={result_id,draft:true}`；服务端读取配置，客户端不能指定文件/工具路径。只提供带 needs_review validation 的 draft_dwg/draft_dxf/conversion_evidence；原 B04 真实 ODA 回读验证保留，AutoCAD 和工艺批准未通过不发正式制造文件。导出进行中 revision 改变则失败、无产物发布。

编辑命令复用 OperationEnvelope/expected_revision/会话权限和幂等校验；worker 在不可变候选 revision 上重放 document_edits，成功且当前才切换 head；取消/失败保留原 head，晚到结果只入历史。直接 revisions API 不允许注入 document_edits，参数修改保留现有人工编辑。history.undo/redo 接受空参数，事务持久化 head/redo 栈；新修改使 redo 分支失效，未删除历史对象。

工程包 b09-state-v1 同时保存 PaintResult、DrawingDocument、构造规则和编辑历史；恢复时校验源模型及资产 hash，创建新 revision 并重绑定区域/图纸/overlay ID。b06-state-v1 空图工程仍兼容。计算成功、规则检查与人工复核状态在 UI 分开；保存/导出均使用后端当前版本。SVG 显式 Y-up，与局部 mm 图纸一致；3D overlay 来自同一保护多边形及 frame。

MCP 增加 satellite_<module>_run（status/cancel），业务工具只返回 run_id，必须查询真实完成再报告成功。控件、图上有界对话及 MCP 调用同一服务器验证器；宿主聊天草稿包含准确 result_id 并重新校验工程/会话。两个固定中文意图用于技术有界输入，不宣称通用自然语言理解；正式宿主接通仍属 B07 缺口。

### B09 R1 工作台会话绑定

首次 URL `session` 与 `/context.session_id` 不一致必须在加载工程前失败关闭；加载或执行中 URL/身份改变则撤销当前页面上下文，清空工程、模型、结果和活动任务引用并禁用操作。晚到响应不得恢复旧上下文、写入保存包引用、下载或发出聊天草稿。页面服务请求及异步副作用执行前后均校验会话；后端原有 owner/session/revision 授权继续有效。该约束不依赖正式 DSH 接入是否完成。


## B10 规则罩形实现（2026-11-08）

BlanketInput新增可选dimensions_mm；Opening收紧为{id,panel,loop}，空开口列表保持兼容，旧无panel的非空开口因未实现过而明确拒绝，不能猜测所属面。新增EditShape、BlanketResult与Panel.side；生产schema副本和消费验证同步。blanket.generate / blanket.edit_shape接入独立worker，新增GET /projects/{id}/blanket-result。Capabilities阶段为B10；B11/B12操作仍不可用。

固定EnvelopeBaseline按原模型、选择、安装frame和规则绑定；尺寸和开口修改不改分母。五面制造BRep与独立封口评价Solid分离，GLB为米/Y-up显示。工程包b10-state-v1从原始源BRep重建并校验参数/基准/资产，保留b06/b09兼容。详细坐标、开口UV、数值政策、候选Panel、后续版本失效及验证门槛见[规则罩形接口](architecture/blanket-box.md)。


## B11 规则平面展开（2026-11-08）

新增 NetSettings/Unfold/EditSeams/EditFixedPoints/NetResult，三个 blanket 操作接入同一版本化 worker；新增 GET /projects/{id}/blanket-net。B10 BlanketInput 构造字段和既有 blanket-result 保持兼容，B11 参数保存于服务端受控 document_edits。Capabilities 阶段为 B11；未实现 B12 UI。

fold 为保留折边，cut 为有配对但明确不连接的裁切边，两者 owner=null/width=0；join 为平面裁开、装配配对、单侧默认15mm加料。配对基于真实世界边端点，默认仅在没有指定 folds 时自动选择广度优先森林。净片域、孔环、分片刚体映射与图纸 layout 分开；接缝环路、平面重叠和全宽搭接冲突都返回定位及候选，不自动缩窄。

固定点使用实际 panel UV，可处于主体或拥有的搭接片；孔内、片外、数值边界拒绝。唯一ID在所有本工程 blanket 修订中保留，删除、撤销、分支或恢复后均不复用。裁切/基面/搭接归属改变重绑同ID；无效点明确 needs_reselection，失败候选不覆盖旧head。b11-state-v1重建原始BRep和展开，保留点ID，更新修订映射。EngineeringBundle.cut_edges扩展为历史EntityRef或B11派生seam ID字符串；seams和净片明细在net_result内保存。

详细请求、坐标、冲突定位、边界策略、数值门槛及B12消费限制见 [blanket-topology.md](architecture/blanket-topology.md)。本批无新的工艺边距或连接强度标准；外部验收缺口原样保留。

B11净片每piece显式输出包含孔和搭接的material_domain及实际面积，图纸排版不参与该域。Seam.overlap_owner_panel、edge.panel和FixedPoint.panel_key引用展开Panel.key；Panel.id/FixedPoint.panel_id仍是当前修订ID。内部保留折线上的已选面固定点可用，切开成为材料边界后重绑失败；外边/孔边按数值边界策略明确拒绝。

B10 BlanketResult.downstream 保留罩形构造阶段的旧字段；工程是否已有当前B11净片以 blanket-net 接口和 revision_id 匹配为准，不能仅检查旧 not_computed 常量。

## B12 多层工作台与绘图（2026-11-08）

`BlanketInput.installation_face` 是可选的精确当前 EntityRef；显式安装面必须对应 installation_frame 的实际设备底面。工作台通过选中底面法向及同实例正交侧面构造右手安装坐标，源模型位姿只读。`blanket.generate` 接受同 model 的完整参数，新参数在 worker 候选修订中重算，成功才发布，失败保留旧 head；仍支持 B10 的已持久化同参数调用。

`drawing.edit_annotation` 与 `drawing.export` 对 blanket 使用精确当前 blanket-net 的 result_id。注释保存在 blanket_net_v1 document_edits 中的 annotations，重展开/固定点/搭接修改可重放；shape 修改仍清空旧净片及相关图纸状态。DrawingDocument 与 cover/net/两视图同 revision；DWG 使用这份 DrawingDocument 和原 B04 转换器，draft:true，真实反向解析辅助验证，不声称 AutoCAD 通过。

二维选择的 `blanket_target` 在 SelectionContext 中使用稳定 Panel.key 和当前 Panel.id/mapping_ref：seam 包含双方边 ID、panel_key、panel_id、mapping_ref 和世界 mm 端点；point 包含 point ID、panel_key、panel_id、mapping_ref、uv_mm 和 position3d。宿主重新从当前工程读取 net 并核验上述字段及对应 FaceRef，不信任 iframe 自报。view_transform 兼容既有 Transform 对象与宿主桥使用的 16 数字行优先矩阵；新 blanket 上下文携带 schema_version:1；local_coordinates 兼容原单点/空值和桥接实际使用的二维/三维点列表。

工程包继续使用 b11-state-v1：持久化源 manifest/源 BRep 资产引用、参数、基准、历史、净片与图纸，恢复时逐个校验受控源/派生资产 hash 并从原始 BRep 重建。是插件的受控工程存储，不宣称外部桌面 CAD 原生参数工程。paint/blanket 独立 session/binding/head/history、选择和草稿，URL session 错配或异步加载期间身份变化均清空界面。

本批真实设备来源是原 satellite-assembly STEP 中四个实际电池模组，提取保留定义、名称和世界位姿，提取前后体积/面积/边界单独核对，来源见 fixtures/manifests/blanket_cases.json。原完整装配因无三角化面被 B02 拒绝的日志保留，未将该完整导入记通过；真实小装配的技术选面也不等于工程师批准工艺范围。

B12 浏览器验收的每份 DWG 与同 revision DrawingDocument、原生 conversion/readback/run 一起归档；两次尺寸变更不仅核对 hash，还从反向 DXF 解析真实 DIMENSION 测量值和毫米单位。三维接缝两条真实重合边使用实线/虚线区分，点和接缝点击区域只是屏幕辅助，不改图纸尺寸。未提交尺寸/包覆/裁切/折叠参数时禁止保存和导出；二维缩放平移不建 revision。


## B13 复杂几何与修订接口

新增 `complex.schema.json`，OpenAPI 组件同步 AnalysisInput、AnalysisResult、RebindInput。现有异步 operation/runtime/host bridge 支持 `geometry.analyze` 与 `engineering.rebind`，沿用 expected_revision、受控模型引用和会话守卫。分析输入为 face_ref、deflection_mm、cuts_u；blanket 可选 envelope_offset_mm。paint 的非空 cuts_u 与 envelope_offset_mm 显式拒绝。输出包含 revision_id/model_ref/source_ref、算法版本、具体测量定义，status=needs_review、manufacturing_approved=false；分析 artifact 不替换当前制造结果。

`engineering.rebind` 输入 source_revision_id，仅允许同模块本分支祖先。唯一原生映射才更新 head；歧义/trim变化/固定点重放失败发布审核历史 needs_reselection，不发布新工程上下文。手动记录、稳定 point ID、源资产、派生 BRep 和旧历史保留。旧 EntityRef 不跨模型修订静默沿用。

BlanketInput 增加 orthogonal_sections_v1；Panel 增加稳定 key，允许复杂多面，opening 引用稳定 panel key。EditShape 增加 allowance，NetSettings 的 separate_panels 在执行时解析为实际 cut IDs。isometric 与 piecewise 明确区分；局部间隙原生失败时以带方法定义的保守区间记录，不伪造精确最小值。详见 architecture/complex-geometry-policy.md。B13 不删除任何原完整验收要求。

B13 开口键的语法仅允许旧 x±/y±/z+ 与 complex-后18位小写hex；是否属于当前制造裁片仍在原生构造时核验。安装底面和任意自由字符串不能成为开口面。


## C09/C10 补充：B07 host-r2 正式账号模式（待平台验收）

已确认的 DSH 0.2.2-rc.1 账号网关不使用原候选 issuer/JWKS 接口；等价安全约束由 [账号适配 ADR](architecture/host-account-r2.md) 的账号上下文、真实 admission/live session、登记公钥断言与一次性回调实现。原 isolated-adapter 保留为显式开发测试模式。正式 `auth_mode=dsh-account` 不接受 development bearer，capabilities 返回 `trusted_host=awaiting_platform_acceptance`。

浏览器在既有 `/api/satellite-{paint|blanket}` 请求携带 `x-satellite-session` 选择当前聊天，服务器必须查实际 SessionStore；不得将此字段作为信任源。`/host-info` 和原生 `satellite_{module}_host_status` 仅返回公钥登记信息。两模块原生 `operation`/`run` 继续使用原 C09 业务 envelope，owner/module/session/当前 revision 全从 Host 和工程服务解析。请求错误、未登记或已撤销身份、不可用后端不降级 DEMO。新工程限定 TEST-qmh-；owner-only 工程支持 operator 降权 read/deny；间接资源和读写都检查绑定，明确的同 owner 工程元数据读取可用于重新绑定。正式浏览器/工具在实际 9999 的端到端验收尚未完成，原 B07 FAIL 与所有下游完整门禁保留。

## B13 R3：完整设备正间隙候选与实际径向接口

`BlanketInput.envelope_policy=faceted_clearance_v1` 消费 `clearance_options={clearance_mm,section_cuts_mm}`；间隙须大于0且不超过10mm，安装坐标X分段须递增、唯一、在原生完整实体内，最多7处。只接受一个完整实例、单位放量和明确安装坐标；不混用单面选择、裁切/折叠/搭接或曲面参数。`EditShape` 同步接受 clearance_options，保持原baseline，成功时使旧净片/图纸失效。底部封口仅供体积评价；实际制造面以保守正间隙证书输出，工艺仍needs_review。

真实motor径向组件仅在显式curved_boundary_rules的boss分类后处理。原生mouth是根部footprint；保护包含完整实际组件的侧壁、台肩和端面。新增SurfaceMapping.kind=PLANE，radius_mm仅该类型允许0，圆柱/圆锥/球面仍须正值；chart_offset_mm不影响世界映射。非支持或多处附着组件拒绝，不将人工分类候选升级为制造批准。每个实际保护面的provenance记录源边容差及输出边界顶点到原生trim的最大距离，属于采样读回量，不是全局误差界。


## B13 R4：可测量安装坐标（工程候选）

`BlanketInput.installation_setup` 可选，完整设备正间隙策略使用 `{x_direction:[x,y,z],rotation_deg,origin_mode,offset_mm:[x,y]}`。世界方向投影到当前精确安装平面，Z取底面内侧，生成右手框架；`origin_mode` 为 `bounds_min` 或 `face_center`，偏移为局部XY毫米。旋转限定±180度，偏移限定±1000000mm。该设置连同最终 installation_frame 持久化，旧调用不带设置时保持既有行为。

`geometry.analyze` 在blanket模式接受同一installation_setup，返回 `result.kind=installation_frame`、原生实例范围、分段X开区间、框架及明确测量定义。不能混用曲面切缝/包络偏移；测量不修改head、baseline或现有净片。选面必须是当前实例的支持底面；零方向、垂直底面方向、无效坐标或过期FaceRef拒绝。生成时从原生几何重新计算，逐向量/原点比对预览（绝对容差1e-8mm/单位方向），防止仅篡改installation_frame。

工作台允许同实例平面法向参考、显式世界方向、反转、平面内旋转、原点参照和XY偏移。变更安装设置清空旧分段、选择目标和待执行修改，隐藏旧罩形/净片并禁止继续编辑、保存、导出；需要重新测量及生成。框架变更建立新基准身份，完整源设备基准体积不靠改坐标扩大；旧固定点/净片不重放。刷新或恢复工程可明确回到已保存修订。会话变化使迟到的分析响应失效。
