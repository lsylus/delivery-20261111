# B05 原生输入边界

当前只交付可独立复验的检测、来源/依赖候选清单、隔离复制、转换预检和 B02 读回检查。没有已选定并授权的 Creo/交换 SDK 执行端，因此没有 operational adapter；不创建空的 creo_worker/exchange_sdk 模块。原生支持清单为空，B05 blocked。

## 检测与清单

`detect.py` 同时检查 UGC PART/ASSEMBLY、NX SPLMSSTR/UG_PART 内容与文件名，保留 Creo 数字保存版本。保存后缀不代表 Creo 软件版本；文件头版本也不代表工具已支持。汇编源码、未知/冲突格式拒绝，骨架等未识别记录保持 unknown。

`inspect_native_manifest.py` 流式 hash 全目录，拒绝符号链接、大小写歧义和路径穿越。`manifest.py` 按当前文件中可见的名称线索递归收集匹配文件，并保留所有同名保存版本，不猜“最新版”。它不是专有格式依赖解析器：历史/二进制记录前缀可能污染线索，匹配不证明真实组件，未匹配不证明真实缺件。

生成的 wrapper 包含符合既有 C01 Schema 的 `source_manifest`，以及单独的 `dependency_report` 和 `geometry`。当前 `load_status=not_opened`；`units/missing_refs/conversion_evidence=null`，实体数、实例数、包围盒、体积也是 null。完整库存 hash、候选 bundle digest 和原厂实际依赖闭包是不同证据。digest 采用按 relative_path 排序、sort_keys、UTF-8、紧凑 JSON 的完整 files 数组 SHA256；不能只 hash 主文件。

`copy_candidate` 只写新的隔离目录，保留相对路径与保存版本，复制前后核对来源及副本 hash；异常清理仅删除本次新建目录。候选 PRT 也不默认是独立文件。当前不提供压缩包解压或任意客户端路径 API。

## 转换和许可

`NativeConverter.probe` 始终如实返回不可用；未知格式、显式缺件、许可拒绝/过期、指定版本范围不匹配和未验证 adapter 各有错误码。`convert` 先验证副本 manifest，再抛 `NativeConversionUnavailable`，不产生 STEP。配置不能把未实现的转换改成成功。

CLI 兼容 B01 `converters.local.json` 的 native 段，保留 DWG 和其他配置；不执行任意命令，不读取凭据内容，不把 endpoint/credential_ref 写入证据。旧 NX worker 的 STEP→热模型 API 不等于原生 Creo 导入器，不调用或改变旧服务。历史 Windows Creo11/NX12 安装记录不代表当前授权执行端可达。

恢复时优先提供一台支持现有 Creo 9.0.8.0 文件的授权 Creo 工作站及 documented loader/export API；也可用具备明确 reader 版本范围及许可的商业 SDK。确认实际部署/许可条件后只实现选中的一个 adapter。须增加真实 native 进程超时/退出/许可失败、缺件、抑制/轻量表示/族表、输出完整性测试。当前 B02 读回子进程有独立进程组、超时 kill/reap；这不是尚不存在的 CAD adapter 的超时验收。

## B02 读回与验收

`readback_native_step.py` 在独立进程调用原封未改的 B02 `read_step`/`read_xcaf_source`，要求非空有效 B-rep faces，并报告实体/面、单位、体积/边界、树、重复实例和 local/world 位姿。`readback_only` 永远不代表 native equivalence；真实转换还需要原厂实际加载统计、完整依赖清单和有依据的案例容差。扁平化结果不能替代装配层级，须完整实例映射或换路线。

当前三个 Creo 候选均为 9.0.8.0。tyy_sl 的五个 PRT 名称线索有匹配，是优先小装配候选，但完整性未证实。星敏存在未解析名称线索。舱板也有历史/外部名称线索。旧 3285 字节 STEP 经 B02 reader 报无可转换根，不是成功产物。NX probe 仅格式探针；另登记真实历史热业务 PRT 的来源，它是 STEP 派生，不证明外部 NX 装配支持。

统一 runner 登记真实来源探测及 native-acceptance gate；缺许可/工具时 probe exit3，runner exit2/status=blocked。测试通过只能证明本批已实现范围，不能把 B05 标 completed。恢复后从干净提交运行 `python scripts/verify_batch.py B05 --report-dir docs/evidence/B05`，完成独立审查。B14/B15 完整原生交付仍受阻；B02 STEP 路线不受影响。B04/B07 仍 blocked/FAIL，最终 AutoCAD 打开、编辑、保存、重开门槛不变。
