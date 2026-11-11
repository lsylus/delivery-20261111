# B01 输入与工具能力登记

本表是2026-11-06库存核查，不是格式支持清单。所有受控原件只读；没有打开CAD装配、执行转换或独立重开DWG。哈希和精确清单以`fixtures/manifests/*.inventory.json`为准。

| 样件/能力 | 已核查 | 尚未核查 | 批次责任 |
|---|---|---|---|
| ZIP/20261010_asm_5_asm.stp | 670820444 bytes，流式SHA256，ISO-10303-21/Creo导出文件头 | 装配加载、单位、实例数、与DWG修订对应 | B02/B06/B14 |
| ZIP/喷漆图.DWG | 2156305 bytes，SHA256，AC1032头 | 可编辑实体、尺寸真值、AutoCAD重开、对应模型 | B04/B14 |
| Star1～4 Creo候选 | 全目录文件名/保存版本后缀/bytes/SHA256，小头识别PART/ASSEMBLY/STEP | 总装主入口、缺件、族表、真实版本支持、原生加载完整性 | B05/B14 |
| G/cases四个original.step | 受控绝对目录、bytes/SHA256、小头识别 | 几何正确性、人工真值、规模与误差预算 | B02/B14 |
| CadQuery2.8.0/OCP7.9.3.1 | Linux Python3.12.14独立新venv及全新复建venv可import | STEP/XCAF功能、原生Creo/NX能力 | B02/B05 |
| DWG转换器/AutoCAD | 未配置、许可unverified | 可用版本、批处理授权、部署及重开 | B04 |
| Creo/NX转换器 | 未配置、许可unverified；不把T的NX探针当已支持 | 工具/版本/许可、完整子装配转换 | B05 |

开发集：Star1、Star2、catch-original、real-thruster、real-gearbox。保留集：Star3、Star4、ZIP STEP/DWG、satellite-assembly。首次登记的selection_spec为null并有原因；实际打开后固化FaceRef+签名和定位规则。未确认字段不填0或空数组伪造真值。

ZIP仍位于Windows `D:/小卫星/插件/新增插件.zip`；inventory中的路径是压缩包成员，不是Linux可直接打开的文件。需要大模型时由对应Batch进行一次受控资产导入并记录源hash，不将文件复制到Git。Star库存中的STEP只是候选对照，绝非已核实同修订。

原ZIP模板保持只读且标记legacy_template_only_not_production_contract。Schema中的产品默认只来自当前docs/contracts.md，不由模板回填。本批输入清单登记不需要商业软件许可，不宣称后续许可已经具备。
