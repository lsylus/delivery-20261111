# B02 第七轮修复独立复审

结论：**FAIL。上轮八项父实体/图层反例与 P2 物理文件重校漏洞已关闭；但新共享策略只核对线型名称，未核对其实际 LTYPE 定义。把当前使用的 Continuous 定义改成虚线后，读回、renderer 与完整 probe 仍接受，DXF/PDF 有效显示不一致。技术闭环未完成，不能标“技术闭环可送人工”。**

本轮仅更新本报告、上轮原字节归档 `docs/reviews/B02-rereview-6.md`、新独立证据 `docs/evidence/B02-rereview-7/`；归档 SHA-256 **`617c324dbd50bd3c62594b3216ec3839a1d5c2656ed025cbe4185df288ac4057`**。未改业务、测试、执行报告、冻结候选、决定或各自 orchestration。未运行 ODA、真实 DWG 转换器或目标 CAD，未借许可、未代签批准，B03 未启动。

## 身份与审查范围

用户交接本地 `2371846ea4be44ed5ad86519f24fee1a78661353`；实际开始 HEAD **`6987bf7b5a79e98010680ef562b9a9bf40340b15`**，其间仅本地调度文档。远端开始 **`1890643b848f9e4c2a9c0d8086f94579c20f4542`**。两端初始均 clean、分支 `codex/b01-foundation`，源码契约指纹一致：**`f532dc2529653cae02ad0bcc01996cdbf801495f97e9af3154ca672866c5b1b7`**。未以纯文档 HEAD 不同判失败。

已读最新执行报告、上轮复审、plan、B02、C02/C05/C06/C07、R02–R04/R07、基线、progress 与当前决定；实际检查 display_profile、readback、renderer、adapter、signature、模板/registry 改动及新增测试。两端未发现适用 AGENTS。执行报告的第六轮归档 `docs/reports/archive/B02-fix-6.md` 保持 `98870e4dae5f3c759d41c3c6b529dd2b9883c76144160dd4dcc70f8210d44677`。

主独立快照 `/tmp/heater-b02-rereview7-_0cc5jjc/snapshot`；显示矩阵另用 `/tmp/heater-review7-display-61e7ep2x/snapshot`。所有反例在隔离副本或新证据内，正常冻结候选只读。首次远端 diff 误用了仅本地存在的上轮提交，退出 128，失败日志保留；随后按远端上轮 `b45d339` 重取 focused diff，退出 0，实际命令见 `binding-analysis.json`，未隐藏失败或改写为成功。

两端分别核对原有 **3,335 / 3,327** 个保护文件，字节全不变；源码 entries 一致。初始差异包括本地独有九份 Windows/运行日志、远端独有根 `.gitattributes` 及原有 state/events，均保留，不用同步历史消除差异。state SHA 分别 `a07b40b803caef6da934cf03b57842ff494bec29319f585e5de81bbeab55ba43`、`df93bfb48ba4d7acf5600b8f509cad250afcff7cd32c1ca36f2664a138ddf57a`。逐项封存与来源见 `evidence-index.json`、`source-mirror.json`；双端独立内容提交及 clean/diff-check 见另行提交的 `git-handoff.json`。

## 独立执行结果

| 验证 | 结果与证据 |
| --- | --- |
| 默认原注册 B01 CLI | **0 / passed**；53 contract + 47 planning、0 skip、10 checks、ECMAScript、独立 wheel 通过；`b01-current/summary.json` |
| 默认原注册 B02 CLI | **2 / blocked**；91 format、191 regression、0 skip；probe 0，dependency 与技术 checks passed；仅 human-gate-0、check-format-gate 阻塞 |
| Linux 独立全回归 | **191 passed，101.33 s**；格式 **91 passed，83.35 s**，见 `b02-current/` |
| Windows 独立全回归 | **191 passed，0 skipped，142.82 s**；运行时 argv/log/xml 见 `windows-results.json` |
| 时间戳 | Windows 五次定向重跑 **5/5 退出 0** |
| 显示类组件检查 | **44 项**，仅正常噪声、显式默认和新增线型定义错误被接受；`display-review.json` |
| 显示完整 probe | **29 次**；26 个应拒绝反例退出 1，两个合理正例退出 0，线型定义反例错误退出 0 |
| 额外粗虚线完整 probe | 同时改首张单页/合并 DXF，全部重渲染、更新 hash 后 **错误退出 0**；`linetype-review.json` |
| 既有 DXF/PDF/颜色负例 | 24 个 DXF 全拒绝；错误单页、单页横移、合并第二页横移均 1；全黄色图层改黑、仅合并第二页黄色改黑均 1 |
| 黄色/黑色框线 | 三单页与合并三页，各 21 段实际端点/颜色匹配通过；`color-review.json` |
| P2 实际 helper | 正例通过；物理文件变异、深层/跨 token/导入、日志/descriptor 变异均拒绝，恢复后通过；`receipt-review.json`、`receipt-supplement.json` |
| B01 原始绑定 | 新鲜原源码 clone 正例通过、十二变异 blocked；`dependency-original-results.json` |
| 当前 registry 根 | fix-7 路径/注册约束通过，污染旧 fix-3 不影响当前证据；`runner-review.json` |
| CLI 矩阵 | 真实六次子进程退出 **0,2,1,1,1,0**，pytest 1 passed；`reviewer-cli-matrix.json` |
| C02/模板只读 | 三页模型及共享语义通过，候选/模板与主快照字节一致；`sealed-facts.json` |

执行器 B01/B02 summary dirty_files 均为空且源码指纹正确。复审 B01 clean；复审 B02 如实仅列前一步产生的 `?? docs/evidence/B02-rereview7-b01-current/`，不冒称全目录 clean，也不误判业务源码脏。`runner-review.json` 继承字段名 `outside_fix5` 实际检查 fix-7 前缀，数组为空。未声称额外精简证据全 CLI 已重跑。

指定九项显示退出仍为 **1,1,1,1,1,1,1,0,0**：MTEXT invisible、LINE invisible、箭头 SOLID truecolor、MTEXT extrusion、背景填充、LINE thickness、0.001 mm 几何差均拒绝，3e-14 mm 噪声和显式默认接受。上轮八项父实体/图层异常全部拒绝；扩展 layer locked/lineweight/linetype/plot、0 图层关闭、缓存/INSERT/SOLID 的 BYLAYER/BYBLOCK 及组合继承均拒绝。共享策略确实补上旧缺口，不能说旧八项未修。

渲染器拒绝的变异保留复制来的 PDF，再真实运行完整 probe 并拒绝；不声称这些异常成功重渲染。渲染成功的正例、新线型错误与几何 0.001 mm 例均重建三页 PDF/PNG 和合并 PDF。35 份完整候选输入全部封存，`probe-candidate-archive.json` 核对所有 manifest artifact hashes 匹配。黄色图层改黑也在 renderer 阶段拒绝，另有仅修改合并 PDF 的独立负例，避免把前置拒绝当成已验证重渲染路径。

真实服务根 `.venv` 的只读 `.tools/uv sync --project service --frozen --check` 退出 0；锁未改，SHA `7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60`。实际版本见 `results.json`：Python 3.12.16、ezdxf 1.4.5、PyMuPDF 1.28.2、fontTools 4.68.0、pypdf 6.21.4、matplotlib 3.11.2。

## 必须修复：[P1] 只绑定 Continuous 名称，实际线型定义漂移仍完整通过

位置：`service/src/heater_drawing/drawing/display_profile.py:27/64/80`，`readback.py:553/737`，`pdf_renderer.py:197/272`，`scripts/probe_formats.py:208`。共享层策略只核对 `layer.dxf.linetype == 'Continuous'`；layer/parent/cache 签名均不包含被引用 LTYPE 表的实际 pattern。renderer 仍直接用实线绘制 LINE/LWPOLYLINE，也不拒绝被改成虚线的 Continuous 定义。新增 parent/layer signature 无法发现这一变化。

独立复现只改**本受控候选当前正在使用的定义**，未增加通用 CAD 要求：

```python
doc.linetypes.get('Continuous').setup_pattern([10.0, 5.0, -5.0])
```

同时保存首张 `CX-29-KR05-XM01.dxf` 和合并 `heater-sample.dxf`；其层名、线型名、实体坐标/颜色/父尺寸/缓存均不改。产品 renderer 重建全部三页 PDF/PNG 和合并 PDF，刷新全部 manifest hash，再执行：

```text
.venv/bin/python scripts/probe_formats.py --fixture fixtures/synthetic/heater_sample.json --candidate docs/evidence/B02-rereview-7/linetype-candidate --profile dxf_pdf_v1 --output docs/evidence/B02-rereview-7/linetype-validation
```

**实际 exit 0、status passed、candidate_immutable/template_immutable true。** 正常 DXF 的编译/解析 pattern 为 `[]`，错误 DXF 为 `[5.0, 5.0]`。独立 `RenderContext/Frontend` 显示矩形、引线及部分尺寸界线变成断线；产品 PDF 仍为连续实线。对照 `visual/linetype-comparison.png` 与变异产品 `linetype-candidate/renders/CX-29-KR05-XM01.png` 已目视检查。只是 ezdxf 独立显示解释，不是实际 AutoCAD 观测。

`binding-analysis.json` 进一步确认：正常与错误 DXF 均 audit **0 errors / 0 fixes**，inspect_dxf 均 passed，`page_consistency_signature` 完全相等。另一个 `[1.0, .5, -.5]` pattern 在独立显示矩阵快照中也被完整 probe 错误接受，整份输入见 `display-full/continuous-definition-dashed/`。这不是 stale PDF、漏更新 hash、坐标噪声或无效 DXF 的假反例。

精确证据：`linetype_review.py`、`linetype-review.json`、`linetype-full-probe.log`、`linetype-validation/probe-result.json`、整份 `linetype-candidate/`、`binding-analysis.json` 及显示矩阵对应 case。

建议对该 profile 实际引用的受控线型表定义做规范化验证/签名，至少确认 Continuous 没有 dash/gap/复杂 pattern；renderer 与 readback 同时采用，单页/合并签名绑定实际定义。保留正确显式默认及噪声正例。不要求实现通用 CAD 线型渲染；拒绝越出受控 profile 的现有定义足以关闭本问题。F04/F05 整类因此仍未闭环。

## P2：本轮关闭，组件与外层能力分开

`dwg_adapter.py` 的 `_runtime_execution_error` 现在每次重算实际 input/output SHA，并与调用方 tuple、封存记录及 size 一起核对。真实普通 Python DXF-copy helper 正例通过；保留真正记录与旧缓存 digest，分别同尺寸改 input/output 字节，**cached/fresh tuple 均拒绝**。删除、原子 replace 同尺寸文件、替换成目录亦拒绝；每一步恢复后正例通过，最终 positive error 为 null。

十五项保留 token 的深层记录变异、跨调用 token、导入 JSON、未执行 DXF 重绑均拒绝；十一项版本字段变异、物理 descriptor/stdout/stderr 改动也拒绝。每调用 token 不同，实际正例/恢复正例证明没有把所有运行一概拒绝。exit 7 保存 stdout/stderr 各 6001 B 并拒绝，0.15 s timeout 后子进程 sentinel 未出现；伪 DWG 的 missing/stale/junk/header/低熵/高熵负例保持拒绝。Windows 改名 Python 仅复制/验身份，未执行；Linux vendor trust 拒绝。

这些是组件与普通 helper 错误处理验证；默认外层 capability 仍 `not_configured`，conversion_run=false，没有真实 DWG 或许可/目标 CAD verified 正例。没有把 Python 版本夹具的 `ODA File Converter FIXTURE ONLY` 字符串冒充 ODA；没有继承别项目授权。

## C07 边界：有效注册窗口与额外变化事实均成立

**没有发现 C07 实质不满足。** 契约原文明确允许真实外部变化记为 `changes_observed/unknown_external`，要求完整 baseline、实际稳定 hash、同 source、时效及重新计算 comparison；没有要求未知外部活动使一个此前有效窗口作废或无限补 after/全量重跑。

`boundary-pending-review.json` 对注册 before/after 执行实际严格验证器：两者同当前源码，coverage 完整，baseline 稳定 hash 匹配，24 h 内；重新计算为 unchanged / 0 changes。注册窗口是 **2026-11-07 22:50:50.694551–22:51:01.196593 UTC**；文件 SHA 为 `7c3891ec2393c1d47f0176532b1a7f73ac97a74c6f63c99588d6e733487c9b68`、`cac42daa6604afa7507575fc56b2e92b257a52d87bbe4cd5da22fd37c2250de4`。

额外 post-run observation SHA `3e5ed8edee28586658c379b5cb53e649ee629453f0aab2ca0ba92bbe52b99d76` 的 baseline 并非上述注册 before。复审从远端 Git `e356248e02832c1294b73bbbe8814f3e2f8b4670` 取回原 baseline 字节，封存为 `post-run-historical-baseline.json`，其稳定 hash 精确为 `ce8bfd0c19e8ac68ac73a4fd7fbb40e73670bf286440047d5da8e34bd879456e`。对 **22:35:52.266667–22:53:05.439238 UTC** 重新计算，确有 `dsh-satellite-drawings` 工作树 state 从 `386135b6020604bb08dd555fe704bd2bead53845534812a7a8aadd5cc08320f3` 变为 `c19edb705cd87d65d5ffa7b5061496db9cd5a2b2396101e4a6725310fb4e913f`，attribution=unknown_external，与原观察一致。

本复审另运行当前真实外部 before/after CLI 各 0，严格验证 passed / unchanged，原证据保留于新证据。上述结论只覆盖各自窗口，**不声称执行者整个工作期间外部项目始终未变**；未回滚或归因外部变化，未修改注册记录来掩盖额外事实。

## 保持通过的发现与限制

| 项目 | 处置 |
| --- | --- |
| F01 | 24 页差异表、349 行、2,238 单元格、34,163 可见字形；展示与数值映射一致、无越界 |
| F02 | 当前字形/箭头独立实测与软件再生成稳定，关闭保持；真实 CAD 未做 |
| F03 | 双引线/尺寸侧别、字形/文字/图框碰撞检查通过 |
| F04/F05 | 旧显示反例已修；新增 LTYPE 定义 P1 未闭环 |
| F06 | 待真实具名 CAD 与工程决定；无代签 |
| F07 | 原始冻结候选/模板与既有文件全部原字节保持 |
| F08 | 三页 C02 通过 |
| F09 / P2 | 物理 input/output 重算及原私有记录防线独立通过，本轮关闭 |
| B01 | 当前绑定正例+十二反例通过；历史认可未替换 |

三候选完整图、原图联系表、覆盖 24 页的六张差异联系表及第 1/12/24 页完整图均目检；未见正常候选裁切/文字碰撞，O3 按 Excel 输出“郑玲”。差异源线段 55/55/65，各匹配 4、未匹配 51/51/61；候选各 21、未匹配各 17，显示集合一致；每页候选文字 41 项。源文字语义仍 unknown/approval，不凭轮廓认定文字准确。

实际 OTF `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`、PostScript `NotoSansCJKsc-Regular`；源 TTC face 2 的 hash `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`，独立 name 表/copyright 确认为 SIL OFL 1.1，未加字体二进制。原 TEXT、缓存 MTEXT、完成 MTextExplode 后实体、再生成各阶段实际解析同一字体，排除不可见 PDF 搜索文字，未沿用旧 fallback 假测量。

129 实体、876 可见字形、12 箭头最大误差 **0.0000170093 / 0.0000172347 mm**，再生成误差 **0 mm**、碰撞 **0**，单页与合并页像素一致。六原生尺寸各两次再生成、保存重开再生成稳定；改定义点宽 +5 / 长 +7 后分别为 **35/57、30/32、105/307**，缓存文本正确，保存重开稳定。不是 CAD 自动关联修改轮廓或实际 AutoCAD 证据。字节副本/平移几何签名控制不是 DXF–DWG–DXF 往返材料。

当前 B01 summary SHA **`14da75e922eae952032639d49211ecf600a696fbb9ef7a2ffdb765a7db6f0e43`**、binding SHA **`3cec8250f337b5d27cba30af4af6e40a689e72f58cb5dcdea6cdbf221451e113`**、运行 HEAD `725982c67c4ab690f90245beea3afd62e1f306cd` 已独立核对。历史认可 B01-fix-2-r2 SHA `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0` 不变；不以当前文档 HEAD 替换登记源版本。

## 当前候选和待签范围核对

下表为已核对的冻结事实，**不是可直接批准的技术闭环包**：

| 文件（相对 `docs/evidence/B02-fix-7/candidate/`） | SHA-256 |
| --- | --- |
| candidate-manifest.json | 216d18c4fd9d29e0a7daaf2966830c812f9be7f3aedfe369a70fcfb657ed8c74 |
| heater-sample.dxf | bcde27d09356a103e85714a44a6a7f58db867b6d5c3914aa4eec332f5e336446 |
| heater-sample.pdf | 2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f |
| reference-difference.pdf | 8410a92af363d4aacdbdd205f160b75fb35e534c2161478291e213154fc452a5 |
| reference-measurements.json | 03ce1cad435a9aeb39bbaf6bf993458b970cf03f3e709181ef7f9090d5aebaee |

逐页 DXF/PDF 等全部精确 hash 见独立 `boundary-pending-review.json` 的 pending.artifact_hashes。模板 manifest `1a1e604066096021c90267b9cfaa5e7dab024abaee33a75a763545e4508c73dd`、DXF `b7a3e7221c002f08c9ebcf9bbc42917cf6c245840ff288c7a02d74c1368aec5d`、layout `d496dc574287bbdba4cace532fe858f1f844d26eb52a15d677367d3315d91f92`、fonts profile `074d234d1881e3aefbe54e10e2c271f7857636d76d48a813f7a191e6ef976a3d` 均匹配。

当前 format/template/human/manifest 的活动引用均切 fix-7，独立扫描没有旧轮次活动引用，human 所列全部 artifact hash 匹配。actor/role/time/conclusion 仍空，AutoCAD 2018 的所有动作 false，approval_claim=none，确实没有批准。待审工程范围是重建黄色框线/标题栏锚点和差异、Noto SC face-2 替代、纸面 **线距 5 / 内伸 10 / 外伸 10 mm** 及三页摆放、原生尺寸更新行为。未来需具名 CAD 产品/版本与环境、人员/角色/时间，精确输入/输出 hash、打开、编辑轮廓/文字/原生尺寸、显式更新/REGEN、保存、关闭、重开、单位/字体/尺寸确认及截图/操作记录；不得从本次软件测试代填。

DWG 首发范围仍 pending_user_decision，推荐延期并保持既有 DXF/PDF 基线；若要求首发 DWG，则需本项目适用授权、真实正反转、确切 DWG 的目标 CAD 编辑保存重开，并成为阻断门槛。新 P1 修复并重建候选后，其文件 hash 与待签绑定也需对应刷新。当前技术 FAIL，不送“只剩签字”的包，不代替用户选择或审批，停止于 B02。
