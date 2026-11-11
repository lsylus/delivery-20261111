# B01 数值、坐标与版本政策

工程长度mm、面积mm²、体积mm³、角度rad；输入单位必须转换并保留来源。4×4矩阵按行存储，作用于列向量，平移在最后一列。frame为原点与右手正交XYZ轴。契约校验以1e-9检查旋转正交性和齐次矩阵最后一行，仅为结构验证，不是CAD/制造公差；镜像、缩放、非有限数值拒绝。

FaceRef以ModelRef中的project/model/revision/assembly_digest加instance/entity/signature定位；revision内稳定不等于跨revision自动匹配。definition与occurrence分离、重复instance_id禁止；跨revision歧义needs_reselection。SourceManifest的assembly_digest定义为：完整`files`按relative_path字典序排序，字段保持relative_path/sha256/bytes，以sort_keys=True、ensure_ascii=False、separators=(',',':')生成UTF-8 JSON再SHA256。包含全部依赖及保存版本后缀，不只主文件。ZIP/Star库存不是已加载SourceManifest，不能伪造确定主装配或units。

喷漆距离严格 `< contact_threshold_mm`，默认0.1mm且阈值可配置。该值绝不是OCCT fuzzy tolerance。contact/hole默认保护外扩3mm，boss默认保护但additional_offset=0，rib不因投影自动保护。方向、覆盖、材料域和阈值不确定区由B08算法验收。schema default不自动注入数据；消费者必须显式初始化字段，不能合并旧template_only值。

多层初始化是XYZ线性各1.05，底面固定、XY居中、Z向上；100方盒为105罩内尺寸、侧隙2.5、顶隙5、体积比1.157625。允许后续用户修改线性系数，禁止把mode换成体积倍率。接缝单侧默认15mm，owner是一个panel ID；fold无自动搭接。固定点使用实际mm域，间距正数，无固定数量。

最终比值含边界`1 <= V罩内/V基准 <= 1.2`。基准包络不可随调整增大；封口只用于计算，搭接重复用布不进罩内体积。B10及以后还必须检验覆盖、穿入、自交、折回，Schema无法证明这些几何事实。

简单解析夹具长度绝对1e-6mm，面积/体积相对1e-6；近零需每例显式绝对界。真实工程、转换和曲面制造公差不能借用此测试oracle；资料不足维持needs_review/blocked，不能调松公差放行。

HTTP 409表示工程expected_revision或幂等键输入冲突；取消状态cancel_requested需执行端结束才cancelled；stale是结果关系，不是worker state。检查、作业、人工批准分别记录。Schema只验证载体与部分一致性，B06真实事务并发行为不能由B01契约测试代替。
