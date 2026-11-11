# B02 独立审查

**FAIL。** 三页真实 DXF/PDF 和原生尺寸已生成，92 项既有测试通过；但模板、技术文字、PDF 渲染、字体选择和验收门槛存在可独立修复的缺陷，不能认定“技术准备完成”。此外，目标 CAD 编辑保存重开、工程审阅和用户格式决定仍未完成。当前不得放行 B04。

日期：2026-11-07（Asia/Shanghai）。仅审查 B02；未修改业务源码、既有测试、执行报告、原样件或 orchestration/state.json，未执行 ODA、未借用其他项目许可，未委派代理。

## 依据、版本与独立验证

已读适用规则（两端祖先及项目内未发现 AGENTS.md）、review-prompt、plan、contracts C02/C05/C06/C07、B02、requirements R02–R04/R07、环境核查、progress、B01 执行交付及最终独立 PASS、当前 B02 执行报告；检查实际代码和提交差异。

| 项目 | 实际核对 |
|---|---|
| 本地根 | `C:\Users\HUAWEI\Documents\ChatGPT\矩形加热器插件\heater-drawing`；Git 顶层为其父目录 |
| 本地开始 HEAD | `1fc2e39be4d12031fb2e0a180a9d8a47a171f033`；业务交付 `9825a51`，执行交接 `504110ce1143e79421a079208d6df37c26ba3a03`，其后仅调度文档 |
| 权威远端根 | `5090-qmh:/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing` |
| 远端开始 HEAD | `e761c435ad97a5b3acf665517ca2f6f091bdf563`；业务/证据提交 `990d3b62b8ccc7ad68219c66bcda3412827232b0` |
| 两端身份 | 分支均为 `codex/b01-foundation`；开始时 status --porcelain 为空，diff --check 退出 0 |
| B02 交付绑定 | 当前源码指纹与原 summary 均为 `ef64d9f7291ac5bc439b9c8d8614f68cb14df1581d0c813496f1c9b4061f7bd3`；原 summary 引用文件 hash 全匹配。不能因它记录提交前 HEAD/dirty 或后续文档 HEAD 不同自动否决 |
| B01 前置 | 只认可 B01-fix-2-r2/summary.json，SHA-256 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`；当前依赖核验通过 |
| 同步与影响范围 | 两端 372 个原跟踪文件逐字节一致（排除 orchestration 和不同仓库根属性）；B02 的 registry/runner 增量及 B02→B99 未注册负例变更已检查；完整 contracts/planning/formats 回归复跑，未用 B01 历史结论代替本轮检查 |

独立证据根为 [B02-review](../evidence/B02-review/evidence-index.json)，原始 argv/cwd/退出码、版本、hash、反例和运行时路径归档映射见该索引。检查入口：

```bash
.venv/bin/python docs/evidence/B02-review/independent_check.py /data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing
.venv/bin/python docs/evidence/B02-review/supplemental_check.py /data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing
```

生成探针会改写受控模板与固定证据目录，因此在 `/tmp/heater-b02-independent-11c5o15t/snapshot` 的独立 Git 副本运行未改 registry 的 B02 runner；副本开始源码指纹与权威根一致。原工程及历史证据只读，前后保护文件 hash 无变化。合成 approved/许可记录明确标为 `SYNTHETIC_ONLY`，只在隔离目录用于反例，不构成人工批准或转换授权。

脚本采集 initial-status 时已创建本轮证据目录，因此日志中的唯一 untracked 项为该目录；本轮创建前的两端 status 已另行实查为空。

| 独立验证 | 结果 |
|---|---|
| 未改 registry 的真实 B02 runner | 2/blocked；DXF/PDF 探针 0、格式失败测试 8 passed、完整回归 92 passed/0 skipped、DWG 探针 2、格式 gate 2 |
| 原件与交付 DXF | 实际读取汇总及三份独立 DXF；AC1032、INSUNITS=4，3 个闭合轮廓、6 条 LINE 引线、6 个 DIMENSION、81 个顶层 TEXT；DXF audit 无错误 |
| 几何及 viewport | 25×25、30×50、100×300 均为真实模型尺寸；原生测量相符，DIMLFAC=1，DIMSCALE=1/1/2；三个命名 layout 的 viewport 高为 297/297/594、纸面 210×297，横向 tile 原点 0/220/440。另保留一个空 A3 Layout1，见风险 |
| PDF/PNG 实物 | 用 Poppler 独立渲染原三页 PDF 和交付三页 PDF，查看六页及技术要求/标题栏裁片；另用 ezdxf addon 独立渲染并查看三份实际 DXF，与交付 PNG 交叉比较。两份 PDF 均三页 A4、无整页位图；这是软件图面观察，**不是目标 CAD 或工程签收** |
| 字段及符号 | 原 Excel O3 实读为“郑玲”，候选 DXF 第二行标审值也是“郑玲”，保留这一有意偏离原 PDF 的修正；三行数量原文存在。候选 Ω/± 可见，无观察到方框；实际字体集合覆盖这些字符，但现有 coverage 探针遗漏正文，见 F04 |
| 独立反例 | 错误尺寸文字/viewport/引线/电阻正文/三角形均被回读接受；空批准、过期且不对应产物的批准被格式 gate 接受；批准延期路径仍被 runner 阻塞；损坏 template.dxf 被 loader 接受；未转换却返回 verified_evaluation_only，64 字节垃圾被转换 helper 接受 |

## 必须修复：执行者可独立完成

以下 `drawing/` 均指 `service/src/heater_drawing/drawing/`；行号以本次交付代码为准。

### B02-F01（高）：模板与固定技术文字不符合基线

位置：`drawing/dxf_writer.py:94–105`、`templates/heater-a4-v1/layout.json` 的 fixed_text/frame_lines/field_anchors，以及当前全部样件。

技术要求第 4 条输出“**聚酯亚胺**薄膜HF”，需求 R03 固定文字为“**聚酰亚胺**薄膜HF”。模板还漏掉原件的“底图登记号、描校、质量、阶段标记、比例”等固定文字和多处分格；把签署标签合成一行，姓名与各标签没有对应单元格。单位名称穿过 x=130 的分格线，独立 DXF 渲染还可见签署姓名/固定标签重叠。外部黄色框线被黑色简化外框替代。不是仅待字体外观批准。

源 PDF 实际可提取矢量线：左登记竖线约 x=25.5129，右标题分格约 x=143.6017；候选改成 30/130，现有“coordinate-measurements”只是重复候选数值，没有逐项原件测量与差异依据。详见 `pdf-inspection.json`、`visual/reference-1-title.png`、`visual/delivered-1-title.png`。

修复/验收：恢复 R03 固定材料文字和模板空栏/标签/对应关系；从真实 PDF 矢量建立来源坐标、变换、原/新值与不确定性表，区分必要规范化与待用户批准差异，不假称原 DWG 原生测量。三页逐字段与八条技术文字核对，实测字形包围盒无越格/穿线/重叠，并重新提供完整对照样件；O3 继续取 Excel“郑玲”。

### B02-F02（高）：PDF 渲染丢失尺寸箭头并改变文字语义布局

位置：`drawing/pdf_renderer.py:21–58`。

尺寸箭头 block 内是 SOLID，递归 renderer 没有 SOLID 分支，全部 12 个箭头从交付 PDF/PNG 消失；独立 ezdxf 渲染可见箭头。TEXT/MTEXT 一律左下对齐且不处理 rotation/attachment，原生竖向尺寸文字 90° 被画成水平，居中数值偏移；还统一乘 0.76 缩字、替换各 CAD 文字样式，PDF 与原生 DXF 图面并不等价。这些问题在既有三页已经触发。

修复/验收：采用能处理实际 DXF 图元/样式的同源渲染路径，或完整支持本模板所用 SOLID、文本对齐、旋转、字体/字高、颜色/线宽及 viewport 变换；不支持对象必须明确失败。独立检查 12 个箭头、6 个尺寸值、竖向旋转/锚点和纸面坐标误差≤0.1 mm；三份单页与合并页一致，不能只验页数。

### B02-F03（高）：长边出线小样的引线与尺寸相交

位置：`drawing/dxf_writer.py:133–170`。

30×50 长边出线页：引线为 `(63,184.5)→(83,184.5)` 和 `(63,189.5)→(83,189.5)`；长度标注放在 x=65、y=162…212，正穿过双引线及尺寸文字区。源 PDF 把此尺寸放在右侧；独立 DXF 与交付 PDF 都能确认冲突。仅检查实体数量不能发现。

修复/验收：按出线侧避让标注，测量引线、箭头、文字和模板禁入区的完整包围盒，碰撞不能记 passed。对这三份 B02 小样记录碰撞明细和零非预期交叉结论；不要求提前实现 B04 完整比例推荐功能。

### B02-F04（高）：声明的字体与实际使用不同，coverage 不覆盖正文

位置：`drawing/fonts.py:16–40`、`drawing/pdf_renderer.py:69`、`drawing/dxf_writer.py:181–182`、`scripts/probe_formats.py:76–77`、fonts.json。

配置声明 Noto Sans CJK SC，但实际 PDF 三页嵌入的是 **NotoSansCJKjp-Regular**；TTC 第 0 面为 JP，第 2 面才是 SC。coverage 把十个字体面的 cmap 合集当作单一字体能力，又只检查 fixture JSON 和 layout.fixed_text，漏掉实际正文的 **54 个 codepoint**（含 Ω、±及材料/标准文字）。critical_symbols 布尔字段不能替代拒绝检查。原生尺寸还引用未在字体清单声明的 `OpenSansCondensed-Light`，PDF 却统一换成 Noto。

修复/验收：锁定并记录实际 SC 字体面/可供目标 CAD 使用的字体文件、全部样式引用、hash 和许可来源；对**最终输出文本及尺寸**在实际选定面检查覆盖，并核对声明 hash。缺正文任一字形必须失败。PDF 实际字体身份与批准候选一致，CAD 字体依赖不得隐式替换；不捆绑未经允许的字体。

### B02-F05（高）：DXF 回读会把错误图纸判为通过

位置：`drawing/readback.py:25–95`、`scripts/probe_formats.py` 的技术 passed 结论；证据 `readback-mutations.json`。

五个独立反例全部被接受：尺寸 text 覆盖为 999（测量仍 25）、1:2 viewport 高从 594 改成 297、一条引线移到纸外、23.52 电阻正文改成 999、闭合矩形换成同包围盒三角形。当前只测极值宽长、总数和 layout 名称，不核对四角直角/实体位置、引线归属方向、尺寸覆盖与缩放、字段文字、viewport/裁切或完整边界。现有 F01/F03 因此被机器宣称通过。

修复/验收：只针对 B02 已承诺元素补足真实四角/无圆角轮廓、每行双引线、原生尺寸定义及显示、layout 单位/viewport/裁切和可编辑文本的验证；保存字段/固定段落到实体 handle 的映射，明确 O3 来源。上述五反例必须失败，正常三页通过，字形边界与碰撞使用实际字体度量。

### B02-F06（高）：格式/人工门槛误放行，同时没有可通过的 DWG 延期路径

位置：`scripts/check_format_gate.py:30–45`、`scripts/verify_batch.py:342–379,618–695`、registry 的 probe-dwg-candidate。

格式 gate 只读 status 字符串。合成 `{"status":"approved"}` 无姓名/时间/产物 hash，甚至 decision 指定 DWG 首版必需且 DWG blocked，仍退出 **0/passed**。第二例的过期、无关 scope、缺失文件假 hash 也通过；通用 human gate 只要求字段非空，实际 runner 接受了这一错误产物绑定。反向问题：即使 gate 接受“DWG 延期”，registry 仍无条件把总返回 2 的 DWG 探针列为必需阻塞项；合成延期 run 只剩这一 blocker，B02 无法按契约完成。

修复/验收：结构化核验具名操作者、有效时间、明确 scope/结论、目标 CAD 版本与编辑保存重开证据、确切当前文件及 hash；生成变化后批准失效。延期须有真实用户决定，可将“未转换且延期有据”判为政策满足，仍保留 DWG 探针 blocked 事实；升级则必须验证许可、真实正反转及 CAD 编辑证据。空/陈旧或错产物批准、pending/rejected、缺 CAD、DWG 必需但未验证均不得 pass。用隔离合成证据验证条件分支，不生成真实签收。

### B02-F07（高）：验证命令会重签/改写受控模板与送审产物

位置：`scripts/probe_formats.py:63–68`、`drawing/template.py:61–67,76–99`、registry 固定输出路径。

probe 在 load_template **之前**重生成 template.dxf 和 manifest，等于先为当前任意 layout/fonts 重新计算受控 hash 再验证；loader 又不核对 template.dxf，损坏为“not a DXF”仍接受。独立 runner 已实证改写模板/manifest 和送审 DXF/PDF/hash（`snapshot-probe-changes.json`）。按执行报告“批准后再跑 runner”会换掉已批准字节；当前 F06 的弱校验恰好掩盖失效。

修复/验收：把候选模板构建与只读验证分开；完整核对受控文件存在/字节/结构及版本，不在验收时自动重签。每 run 独立输出目录、保留历史；人工审核绑定冻结产物，最终验收应验证同一组字节。模板任一受控文件缺失/篡改必须失败且不改输入；只读重验后已批准文件 hash 不变，新生成结果不能继承旧批准。

### B02-F08（中）：小样自创了与 C02 不兼容的页面接口

位置：`drawing/sample.py:11–53` 及 writer/readback/render 的页面边界。

实际用 SamplePage(index,row_id,fields,denominator)，缺 C02 DrawingPage 的 revision/template hash、Scale、geometry、placement、checks、fixed_text_version；几何/文字又在 writer 中解释。三个样本均不能通过既有 DrawingPage 模型（每个 10 项结构错误），与 B02“早期 DrawingPage 使用 C02”明确约束相违背，后续不能直接消费。

修复/验收：仅将早期样件规划结果接入现有 DrawingPage/共享语义契约，提供明确的测试 fixture 修订/hash来源；DXF/PDF 消费已规划几何和位置。三份页面通过公开 Schema 与模型，共用字段/几何并保留 1:1/1:2 结果；不用实现 B03 导入或 B04 完整排版。

### B02-F09（中）：DWG adapter 的 verified 状态和输出验证不真实

位置：`drawing/dwg_adapter.py:35–70`。

仅两字段 project/evaluation_authorized 元数据加任意可执行文件（独立例用 Python），没有一次转换证据就返回 **verified_evaluation_only**。普通 Python 写入 64 个 x，helper 也返回成功；未检查 DWG 文件头、回读，未持久化 stdout/stderr，超时没有 C06 要求的进程组清理。这里没有运行任何真实转换器。

修复/验收：授权可用与真实验证状态分开，无转换证据只能 available_unverified；固定命令 helper 验文件头/真实新输出、记录失败日志并清理子进程，只有规定语义验证完成才能升级状态。用普通独立 helper 测试垃圾/陈旧文件、失败与超时，不需调用 ODA。当前无本项目许可继续 disabled/blocked，不能为修复本项擅自开展商业转换评估。

## 只能由用户／目标 CAD 环境补齐的门槛与剩余风险

- 当前目标 CAD 仍未提供；需命名工程审阅人，在 AutoCAD 2018 或用户明确批准的目标 CAD 对**修复后的确切 DXF**编辑轮廓、文字、原生尺寸，显式更新标注、保存重开，记录版本、人员、时间、前后 hash、截图和结论。软件回读/ezdxf 渲染均不能替代。
- 修复并独立复验技术项后，提交清晰的新旧对照，再取得模板、实际字体替代、引线 5/10/10 mm 的工程批准和基于新证据的 DWG 延期/升级决定。当前 pending 记录保持真实；不能把既有 DXF 基线当成新延期批准。
- 原 DWG 尚未原生测量；PDF 纸面坐标与原 CAD 坐标关系需明确保留不确定性。汇总及单页 DXF 另有默认空 A3 Layout1，需清理或明确排除打印，避免目标 CAD 中误选空页；原 PC3/CTB 不存在，实际目标 CAD 打印映射仍待验证。
- 不要求 B03/B04 的未实现业务功能；以上要求均针对 B02 实际样件、模板、最小接口和已承诺的验收机制。修复后新证据必须绑定最终源码/模板/字体及确切样件，重新独立审查；历史 B02 执行证据保留。

## Git 交接

本轮只提交 `docs/reviews/B02.md` 与 `docs/evidence/B02-review/`。两端原业务/测试/执行报告/历史样件和 state.json 保持开始字节；保护清单及两端镜像检查见 evidence-index。提交后分支、HEAD、status --porcelain 和 diff --check 的实际结果记录在同目录 `git-handoff.json`；随后只提交该记录，最终 HEAD 以两库 git log -1 为准。完成后停止，不进入后续 Batch。
