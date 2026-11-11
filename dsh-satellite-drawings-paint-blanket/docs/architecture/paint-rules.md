# B08 平面喷漆规则与生产边界

实现版本 `b08-planar-v1`，输入规则版本保持 `paint-v1`。B08只实现平面算法及其B06受控worker入口，不实现B07视图、B09交互或DWG闭环。

## 几何事实与业务判断

输入为B06当前ModelRef的受控BRep资产和B02 mesh-map FaceRef。只装载物理leaf occurrence，分别应用world transform，不把装配aggregate重复计入。检查资产hash、字节、面顺序与类型/面积/重心；不重绑旧引用。原生操作前复制拓扑，保留输入BRep字节和装配位姿。

允许一个或多个同向共面目标；不同平面和非平面目标明确needs_review。UV使用目标面中心、投影世界X（接近平行时Y）及右手法向建立坐标；显式scope_boundary使用该坐标。outerWire与innerWires构成真实材料域，开槽属于外轮廓凹口，不填补、不闭合成板。B08不猜测所有凹口都应额外保护。

每一源实体先调用B03 measure_shape_pair，检查有效性、真实距离与交体积；大于1e-9 mm³穿透为fail，不能作普通接触。候选源面必须为相反朝向平面，单位法向向量之和的模≤1e-10；不能仅凭接近-1的点积判定均匀间距。以法向误差乘整个面包围盒对角线，界定面内各点相对重心的间距偏差；上界>1e-7mm则needs_review。法向平面间距严格小于配置阈值。距阈值±(1e-7 mm+该局部偏差)的不确定区不输出普通接触，记录needs_review；0.100mm等值被排除。斜面或近接触曲面不猜测完整脚印，记录局部间距未知。侧边近邻和同向面排除。

在已验证平行平面之间沿目标法向平移源面，再使用B03真实面片Common获取局部覆盖。记录双方FaceRef、gap、normal dot、投影方向、投影前Common是否为空、每片面积。0.099mm的真实Common为空，但投影后得到实际100mm²脚面；绝不使用整机凸包或包围盒代替。B03 fuzzy保持1e-7 mm，不设成业务0.1mm。

每连通片独立round buffer默认3mm，并clip到真实材料和用户范围。只有交叠面积大于1e-9 mm²才建立合并连通边，单纯相切不合并；合并保留各贡献类型和多对多source/provenance。混合类型region的兼容kind为manual，真实来源在contributor_kinds/provenance，origin仍独立表示计算或人工分类。

## 孔、凸台、筋及覆盖

已验证通孔保护直接取目标面实际内环，向材料侧扩3mm；阴影减去孔内非材料。台阶/沉孔取被选面的实际口部。相邻边界高于目标面时不能当成孔：查找源BRep上方同向平面cap。单一圆形直壁、同投影cap的标准整体凸台自动保护实际cap，不默认再扩3mm。cap用自己的实际高度/材料域生成overlay；二维是法向投影，保留来源和高度。cap上的附加offset仍裁剪到实际cap，不向基板隐式增加保护环。

非标准凸台/筋不依据长宽比强猜分类。PaintOverride必须含id、version、model_revision、精确face_ref、classification、非空reason；支持boss/rib/contact/exclude/unknown。整体筋按cap面分类为rib后保持可喷，分离安装特征按实际贴合面分类；没有因“看起来像筋”自动全投影保护。未使用覆盖、重复分类、旧修订、歧义都needs_review，禁止悄悄重绑。特殊工艺边界和制造公差需要实际工程证据，合成解析验证不代表制造批准。

## 数值、预算及输出

源曲线按最大弦差1e-7 mm采样，offset每四分之一圆2048段，解析面积rel 1e-6、关键长度abs 1e-6 mm、近零abs 1e-9验证；这不是制造公差。预算默认10000 pair、500000点、60秒；B06外层独立进程还有硬timeout/内存限制。预算耗尽或原生失败丢弃局部区域，返回明确needs_review/failed，不填空pass。

PaintResult含revision/model/status/regions/diagnostics/checks/drawing_document/overlay/evidence和数值策略。DrawingDocument的hatch及overlay都直接来自同一组region loops；不从截图反推。检查通过、作业完成和人工批准分离。

POST operations的paint.generate只接受已保存revision的parameters/selection/overrides，CAS与幂等沿用B06。HTTP线程不导入CAD。worker对所有资产重新校验，publication核对schema、revision和同源drawing。passed可成为当前结果；needs_review是明确draft，仅入历史；failed保留具体检查但不发布任何产物。旧完整结果仍可按run读取，失败/取消不覆写。

EngineeringBundle沿用B06保存源资产引用、参数、分类与revision；可恢复并重新生成。完整交互编辑、把派生图纸嵌入工程包以及最终DWG由B09完成。真实宿主身份仍未配置；B04仍blocked/独立FAIL，最终AutoCAD打开、编辑、保存、重开不得降级。

生成区域及图纸实体ID包含engineering revision，避免删除后在另一修订复用；同一revision重算保持对应关系。


## 独立审查 R1 收紧

四项反例固定在tests/paint/test_review_regressions.py并强制登记到B08 runner；review-regressions.json保存真实重算结果和原审查hash。下侧/上侧不确定区端点、稍内/稍外、局部deviation均测试。端点采用直接相减/相加及8 ULP外向保护，避免abs(gap-threshold)的消减误差。

孔分类必须存在真实反向面内环出口，沿出口到目标面挤出实体柱，再与源BRep Common确认直通空腔。已知通孔、台阶通孔和沉头通孔可自动处理。盲孔、矩形盲袋、双面盲袋中间残留材料均不能自动kind=hole；单一匹配底面FaceRef的人工hole/exclude策略可显式确定该口部工艺，其他情况仍复核。

覆盖ID在Schema扩展与独立运行时均唯一，应用追踪以完整覆盖记录为键。扩展x-uniqueBy:id在项目两套验证器和跨Schema引用中强制执行，不能仅使用忽略扩展的第三方普通验证器。

预算为全局累计的保守上界：每次B03调用前预留整个Cartesian面对扫描；即便B03没有进入fallback也不退还。不会按occurrence刷新上限。五脚/100pair反例最多进入两次36面对扫描，第三次进入前返回budget_exhausted并清空所有部分区域；计数包含本地检查和合并开销，接受计数不超过上限。
