# 项目与需求核查基线

核查：2026-11-06；操作仅限本机文档/ZIP读取、SSH读取Git状态和源码、文件头及目录枚举。未运行CAD/测试/转换、未安装/部署、未修改任何远程文件。下面是计划依据，不是已通过的新功能证据。

## 路径与源码状态

| 别名 | 绝对路径 | HEAD / 状态 |
|---|---|---|
| G | /data/qmh/satellite-plugins-20261029/dsh-satellite-geometry | 50804c552366acc3b45e4ba92640f49eb4fe3fbe；finalize-20261029；clean；plugin0.3.8 |
| T | /data/qmh/satellite-plugins-20261029/dsh-satellite-thermal | b8ea81ae1212f3cfd6da9a3b2af50281d3083378；finalize-20261029；clean；plugin0.2.6 |
| S | /data/qmh/satellite-plugins-20261029/microservice-refactor-shared-core | 29fecb3bc55e114c766b1553b86d8adaa85dbca5；work/shared-core-20261103；clean |
| H | /data/qmh/satellite-plugins-20261029/microservice-refactor | 283a612693e50c02479f22f5a3cd371b9f053ff7；master；153条未提交变更，不触碰 |
| LOCAL | C:/Users/HUAWEI/Documents/ChatGPT/插件 | Git master无提交；当前已有用户材料均未跟踪，不清理、不提交无关文件 |
| ZIP | D:/小卫星/插件/新增插件.zip | 116928155 bytes；原件只读 |

SSH别名5090-qmh在当前Windows SSH配置可用；后续新环境如无别名，使用已配置的远程访问方式，不把密钥写入计划。目标uname为Linux x86_64，平台入口http://10.110.10.11:9999/。登录页可达是前期核查，不等于安装权限或当前业务健康。本次未打开业务会话。
本地当前工作区及祖先、远程/data/qmh祖先和四个仓库排除依赖目录的AGENTS.md均未发现；实施时重查，不假定未来仍无指令。

S已从旧审计49142be推进到29fecb3；最新日志含manifest shell reader及缓存身份去重。新开发应固定所选函数的来源commit，不把“最新”当稳定承诺。

## 原始需求及冲突处理

ZIP内 `新增插件/references/AI图纸技术要求.docx`：正式要求含stp/asm/prt、实际接触距离<0.1mm、保护3mm、孔凸台阴影、可编辑DWG及AutoCAD打开、多层三维可调片体/裁切/展开、包络体积比1～1.2。本轮从原DOCX正文重新读取。
ZIP内CODEX_WORK_ORDER.md、requirements_traceability.md和templates是旧建议，不能覆盖用户“仅计划”指令，也不能覆盖后来确认的线性1.05、15mm搭接及插件内三维编辑。
原文没有完整工程公差或所有复杂曲面展开方案。不能伪造已确认规格；相关算法由开发批实现、证据不足的工艺差异具体呈报。

## 演示基线

ZIP的frontend/dist/paint/index.html、blanket/index.html和assets/app.js、drawings.js、cad-scene.js是交互原型；preview/*.html为自包含派生页面。
app.js中modelPanel/refresh/run/cleanState/select3d/selectRegion/fixedPointClick/checksPanel是迁移职责入口。模型上传只展示名称，run使用约430ms定时器，DWG按钮禁用；没有CAD后端或可直接安装的插件清单。
- app.js SHA256：a2b7689f68ce493060b49a1da2ca191276fa1e02b1eb8f1dc09e188ba1a8b7f7
- drawings.js SHA256：f58a652bfe02bf30d0f0796850680707bc22522990de2ff63887314369c7bc7d
- blanket模板SHA256：46d53dc86fbf1bfc36937d6706793620216cdce881dda9c8b354e86bffb11b1c
保留demo与live隔离、排除/复跑保留、撤销重做及图纸修改语义；不是复制整段伪计算。两个旧前端分别用Three0.184与0.174，需统一新项目依赖并验证。

## 可复用源码锚点

以下S路径均相对S/cad-assembly/：
| 文件/符号 | 本次观察 | 计划使用 |
|---|---|---|
| backend/geometry/xcaf_source.py:174 read_xcaf_source | XcafSourceGraph持有document、节点、occurrence/definition、本地/世界变换；引用geometry.transforms | B02提取中立读取，不继承旧公开ID及选择策略 |
| backend/geometry/bounds.py | BoundsStrategy、measure_shape_bounds、bounds_gap | B02保守/精确策略分别保留 |
| backend/geometry/transforms.py | RigidTransform及location/shape变换 | B02，不修改源设备姿态 |
| backend/geometry/solid_pairs.py:205 intersect_face_patches | completed+patches；fuzzy=1e-7或None、最小面积1e-7 | B03中立原语，B08另做近接触脚印 |
| backend/satellite_geometry/modeling.py:163、290 | 两处调用公共面片函数 | 只读对照，不能迁移整套业务存储 |
| backend/geometry/step_serialization.py | 引用topology及backend.infrastructure.files.file_sha256 | B02解除旧files依赖，保留读回语义 |
| backend/geometry/glb_serialization.py | 同样引用旧file_sha256 | B02解除旧依赖，显示网格另附FaceRef映射 |
| backend/app/geometry_jobs.py | 依赖geometry_bindings、runtime、JobStore及账号上下文 | B06只参考语义，不整体导入 |
| backend/tests/test_xcaf_source.py、test_xcaf_characterization.py | 覆盖树、位姿、重复实例、STEP读回及ID策略差异 | B02特征化依据 |
| backend/tests/test_solid_pair_characterization.py、test_solid_pair_measurements.py | 距离、接触、L支架误包络、mixed topology | B03特征化依据 |

G/T的plugin/package.json、cordis.patch.yml、src/{index.mjs,client.jsx,host-runtime.mjs,workspace.mjs,chat-bridge.mjs}和mcp/server.mjs本次重读。宿主模块从profileContext.installAnchor解析，认证代理放服务端；G/web/src/Viewer.tsx可参考GLTF显示与高亮，但精确面映射需新增。
G/plugin/src/selection-context.mjs、selection-contract.mjs为选择语义参考。旧cad-bridge关联服务上下文，不代表已存在桌面CAD/DWG双向同步。
旧报告中的测试通过数仅历史记录；本轮未跑任何测试，不能沿用作新批次通过证据。

## 已有样件与限制

1. ZIP测试算例/20261010_asm_5_asm.stp，670820444 bytes，Creo导出AP203；喷漆图.DWG，2156305 bytes，AC1032。修订对应关系未验证，不能直接当已匹配真值。
2. G/runtime/tianyuan-geometry-20261008/inputs/Star1～Star4：
   Star1、Star2各2083 PRT及183 ASM条目；Star3、Star4各1380 PRT及182 ASM条目。含保存版本和重复，不是独立模型计数。
   - Star1/舱板a.prt.5：128594 bytes，#UGC:2 PART。
   - Star1/星敏a.asm.5：137523 bytes，#UGC:2 ASSEMBLY。
   - Star1/tyy_sl.asm.5：74218 bytes，头含Creo 9.0.8.0；不是已确定的总装入口。
   - Star1/star1_original.stp：492990019 bytes，候选对照；未验证同修订和引用完整性。
3. G/runtime/tianyuan-geometry-20261008/creo-conversion-test/含j30j-9zkp3d_1_1.stp及导出日志；日志的67个实体未显示B-rep类型，不能因进程结束断言有效几何。
4. T/runtime/nx-probe/probe.prt：32610 bytes，SPLMSSTR/UG_PART；同目录probe.py用NXOpen创建并保存，probe.json记载后续FEM失败，可能无业务几何。其他NX产物也需筛选，不以这些探针证明外部NX装配支持。
5. T下发现的3个.asm是node_modules/koffi汇编源码，不是CAD。厂商识别必须看头和来源。
6. G/cases/catch-original/original.step、real-thruster/original.step、real-gearbox/original.step、satellite-assembly/original.step可作STEP候选；用途、规模和真值由B01/B14登记。
7. 当前本机曾发现D:/freeCAD安装，但未验证格式/出图能力；没有纯开源全面读取Creo/NX原生文件的已验证路线。HOOPS/CAD Exchanger或有许可原厂CAD是候选，不等于工具已可用。

B01生成case manifest，B05选择最小完整子装配；保持原件只读，将依赖工作副本写到新受控目录，不把整个Star目录无审计复制进Git。

## 本轮检查范围的限制

未重新验证商业许可、SDK安装、AutoCAD可用性、完整装配打开、实际DWG输出或任何新插件性能。这些属于各Batch的真实验收，不能从源文件存在推导出可运行。
