# B02 geometry-core v1

入口 geometry_core.read_xcaf_source(path, options=...) 返回worker内XcafSourceGraph，强引用document及native shapes；同源definition和occurrence分离，不含服务账号/公开旧ID。graph.source_sha256固定读取内容。发生外部STEP document引用、null、空输入、截断或源变化时失败；多文件资产由后续导入层解决，本批不默认为完整。复杂STEP其它未识别外部引用形式仍需后续资产安全审计，不能直接暴露任意服务器路径给用户。

load_model_snapshot(path, *, project_id, model_id, model_revision, asset_id, output_dir) 返回可JSON序列化C01 ModelSnapshot v1，同时在独立输出目录写snapshot.json、shapes/def-N.brep、model.glb和mesh-map.json。调用者必须提供新的run临时目录；函数不负责HTTP、资产登记或原子发布，B06在完整验证后发布，失败目录不得发布。身份和revision由调用者提供；digest按C01单文件manifest计算。源名字优先occurrence再definition，缺名才使用occ-ID；空原始名字在graph中仍保留。源单位在manifest记录，native geometry全部mm。source filename及输出目录必须由上层受控资产系统决定。

tessellate_with_face_map(graph, model_ref, destination, tolerance_mm=0.1, angular_tolerance=0.1) 返回GLB/mesh-map文件引用、hash、bytes和三角形数。原shape复制后才网格化，不修改源document形状。每face一个primitive，不做合并优化；映射键为GLTF原始node/mesh/primitive及primitive内triangle索引。Three GLTFLoader可能为一mesh的多primitive创建Group，消费者使用parser.associations恢复原索引，不使用场景遍历顺序。GLB POSITION是world-mm；scene根矩阵转换至标准米/Y-up。不可再重复应用snapshot.world_transform。工程/BRep仍为右手mm/Z-up。法线平面为有向法线，非平面为null；signature有类型/面积/重心/邻接。

resolve_face要求完全相等的ModelRef和GLB hash；跨revision、不同GLB、越界索引及歧义均needs_reselection。Face ID只在本次revision中稳定，不能跨导入/重算猜测匹配。tolerance为显示网格偏差，不是制造公差。wire/point-only叶节点无可选面，本接口明确拒绝；不是本批支持场景。

write_step_graph导出保留的整份XCAF document（名字/层/颜色模式保留），拒绝覆盖源路径。write_step_shape是单shape工具。read_step/read_step_summary真实native读回，拓扑是unique子形状计数，volume_mm3仅对solids求和，开放面不赋予实体体积。inspect_step输出completed=false+error，成功包含hash、units、bounds、topology与volume。STEP文件导出bytes因时间戳可变，每次验收绑定实际hash。GLB和mesh-map确定性测试在同一版本/参数下完成。

所有重型native工作运行在隔离worker进程；本批未建立HTTP服务或B06任务管理。库与CadQuery/OCP及numpy一起按uv.lock打包；不能通过旧源码PYTHONPATH启动。独立安装测试使用uv --reinstall-package刷新当前包构建，避免旧本地wheel缓存。

B03/B05/B06可以使用上述接口；不自动启动后续批次。B04保持blocked/FAIL，DWG/AutoCAD最终验收要求不变。


## B03 neutral pair primitives

Import `geometry_core.solid_pairs` in a controlled worker. `intersect_face_patches` keeps C04 defaults and its three states. `measure_shape_pair` requires explicit intersection search and zero-volume settings; returns distances, volume, optional common/planar area and separate input-validity facts. It raises a stage-bearing SolidPairMeasurementError for incomplete work. `measure_planar_contact_area` returns a scoped PlanarContactMeasurement, not the source module's bare float/None. Partial scans discard area. See C04/B03 in contracts.md for exact fields and handling.

Normal results use the same OCCT native algorithms as the fixed source. Failure-state hardening and pre-build non-destructive setup are intentional differences, recorded in evidence/B03/feature-differences.md. The library has no business IDs, old backend imports, worker scheduler, 0.1mm classification, or 3mm protection rule. No old or future business caller has been switched in this batch.
