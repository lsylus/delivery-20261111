# B02 第六轮修复独立复审

结论：**FAIL。指定九项显示反例及上一轮运行记录篡改已修复，但尺寸父实体/图层的有效显示仍能绕过完整 probe；另发现运行记录校验器对物理输入输出的组件级重校限制。不能宣布技术闭环，不能作为仅待人工批准的交付包。**

本轮仅更新本报告、第五轮报告原字节归档 `docs/reviews/B02-rereview-5.md`、新证据 `docs/evidence/B02-rereview-6/`。归档 SHA-256 为 `b28ec135dff8165528b20004ac35fafaaf02cb58c5957dc6cacf69ca89f396ee`。业务、测试、执行报告、冻结候选/模板、决定与编排文件均保持原字节；变异在独立副本或本轮证据内进行。未运行 ODA、真实转换器、目标 CAD，未借许可、未代签批准、未进入 B03。

## 审查身份与封存

用户交接本地 HEAD `e250081b2580189a680ca16912f51476b4301ebf`；实际开始为 `2ae589c8cd57264c66ba163f5aa27ca999287b35`，其间仅调度文档。远端开始为 `0e3f7046b999dfe31451c723ca0791f9dee35bb0`。两端分支均为 `codex/b01-foundation`，源码契约指纹均为 **`e96fdcc246ba0cc63bcd9eea677e56d7966b1673ab13aa480baa270a636ed0c1`**；未以文档 HEAD 不同机械判失败。

冻结候选目录 `docs/evidence/B02-fix-6/candidate/`：

| 文件 | SHA-256 |
| --- | --- |
| candidate-manifest.json | b87e9dfa1acdc7ae3cc2824f52e0eeccb11c3146f776c79e4e318b59f328fc8a |
| heater-sample.dxf | 6d83f17e8c8007cefc0594a33f0ec78951469e46d15e763fe959e100ed4b672a |
| heater-sample.pdf | 2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f |
| drawing-pages.json | 89690ad613a119350abf595a59b9ee4ba4d2224c8b36a69831e53bfda7be6fdc |
| reference-difference.pdf | 624d8547ace7ed6e9db35adc6b96c6d62a46c9f8b0a511493a9f46408c6859b5 |

模板 DXF 为 `b7a3e7221c002f08c9ebcf9bbc42917cf6c245840ff288c7a02d74c1368aec5d`。`sealed-facts.json` 核对整个 candidate/template 与执行快照完全一致。两端分别保护原有 **2,515 / 2,516** 个文件；逐项终检见 `local-protection-final.json`、`remote-protection-final.json`。各自 state/events 历史与远端独有根 `.gitattributes` 保留；state SHA 分别为 `deb49a86a04d0e7b8f7ab0e32dd7ebd16e91c5cdde70166a2b531e3a1516e2e6`、`df93bfb48ba4d7acf5600b8f509cad250afcff7cd32c1ca36f2664a138ddf57a`。

已读 plan、B02、C02/C05/C06/C07、R02–R04/R07、基线/进度/决定、当前与认可历史 B01、本轮执行报告、上轮复审，检查实际修复 diff、实现与测试；未发现适用 AGENTS。主快照 `/tmp/heater-b02-rereview6-yh6ebvym/snapshot`；显示反例另用 `/tmp/heater-review6-display-d765he1v/snapshot`，避免并发变异污染默认 runner。原 argv/cwd/退出码/日志、候选及归档映射见 `evidence-index.json`；两端独立内容提交及干净状态由后续单独提交的 `git-handoff.json` 绑定。

## 独立执行

| 验证 | 实际结果 |
| --- | --- |
| 原注册默认 B01 CLI | **0 / passed**；53 contract、47 planning、十项检查、ECMAScript、独立 wheel 安装通过 |
| 原注册默认 B02 CLI | **2 / blocked**；75 格式、175 全回归通过，0 skipped；DXF/PDF probe 0；human-gate-0、check-format-gate 阻塞 |
| Linux 默认 B02 全回归 | **175 passed，0 skipped，97.69 s** |
| Windows 完整回归 | **175 passed，0 skipped，131.02 s，退出 0**；原始 log/xml 与运行时命令索引保留 |
| Windows 时间戳五次重跑 | **5/5 退出 0** |
| 真实外部边界 before/after | 两条 CLI 0，严格验证 passed / unchanged |
| 已有 DXF/PDF 反例 | 24 个 DXF 全拒绝；错误单页 PDF、单页横移 100 mm、合并第二页横移 100 mm 均完整 probe 1 |
| 黄色框线 | 三单页与合并三页，各 21 段实际端点/颜色均通过；全候选黄色改黑、仅合并第二页黄色改黑均完整 probe 1 |
| 指定九项显示反例 | **1,1,1,1,1,1,1,0,0**，详情如下 |
| 扩展显示反例 | 29 项组件检查、20 项完整 probe；新增八项父实体/图层变异错误通过 |
| B01 原始绑定 | 新鲜原源码副本正例通过，十二项变异全部 blocked |
| 当前 runner | fix-6 注册与路径约束通过；污染旧 fix-3 不影响当前证据；执行器及复审 B02 输入全部来自 fix-6 |
| CLI 子进程矩阵 | `tests/planning/test_b02_cli_matrix.py` 1 passed，实际六次 CLI 退出 **0,2,1,1,1,0** |
| C02 | 三张当前 DrawingPage 模型及共享语义均通过 |

执行器 B01/B02 summary 的 dirty_files 均为空、源码指纹为本轮值；复审 B01 clean，复审 B02 如实记录前一步生成的唯一未跟踪目录 `docs/evidence/B02-rereview6-b01-current/`，不将其称为业务源码脏。`runner-review.json` 的继承字段名 `outside_fix5` 实际检查的是脚本中的 fix-6 前缀，数组为空；原始记录未事后改名。本轮没有额外声称精简证据后的完整 CLI 或额外合成全政策套件已经重跑。

指定九项均刷新单页及合并 DXF 的相关 hash，并真实调用 `scripts/probe_formats.py`：

| 变异 | 渲染阶段 | 完整 probe |
| --- | --- | --- |
| 缓存 MTEXT invisible=1 | 拒绝 | 1 |
| 缓存 LINE invisible=1 | 拒绝 | 1 |
| 箭头 SOLID true_color=0xffffff | 拒绝 | 1 |
| 缓存 MTEXT extrusion=(0,0,-1) | 拒绝 | 1 |
| 缓存 MTEXT 背景填充 | 拒绝 | 1 |
| 缓存 LINE thickness=10 | 拒绝 | 1 |
| 缓存 LINE 改 0.001 mm | 三页重渲染成功 | 1 |
| 缓存 LINE 仅 3e-14 mm 浮点噪声 | 三页重渲染成功 | 0，合理 |
| 显式填写默认显示值 | 三页重渲染成功 | 0，合理 |

前六项渲染失败后保留复制来的 PDF，再执行完整 probe，读回检查亦拒绝；**不声称这六项成功重渲染**。新增 entity transparency/ltscale、组合缓存异常完整 probe 也拒绝。所有渲染成功的反例均重建三页 PDF/PNG 及合并 PDF；20 份显示候选和 5 份 PDF/颜色负例的整份输入均封存，`probe-candidate-archive.json` 逐项确认全部 manifest artifact hashes 匹配。

真实服务根 `.venv` 的 `.tools/uv sync --project service --frozen --check` 退出 0；没有改锁或拿审图临时环境替代依赖验证。锁 SHA 为 `7efdee490291a926bb68b2d3b53ce6efe3859ef4715609acfd3c31a40c5a0b60`；Linux Python 3.12.16、ezdxf 1.4.5、PyMuPDF 1.28.2、fontTools 4.68.0、pypdf 6.21.4、matplotlib 3.11.2，实际命令及环境见 `results.json`、`windows-results.json`、`receipt-review.json`。

## 必须修复的发现

### [P1] 父实体/图层有效显示遗漏，错误候选仍完整通过（F04/F05）

位置：`service/src/heater_drawing/drawing/readback.py:122/140/584`；`pdf_renderer.py:33/57/227/254`。新缓存签名覆盖了实体常见显示字段、MTEXT 格式和未知显式属性，旧负例已实质修复。但 DIMENSION 本体仅比 `_cache_display_signature`，未验证其 ACI color/lineweight；缓存签名的原始 layer/color 字段没有解析父级和图层的有效状态。渲染器只检查实体自身，`_stroke_color` 对图层颜色取 abs，忽略图层 off/frozen、truecolor、transparency 等。

在第一张 `CX-29-KR05-XM01` 的单页与合并 DXF 同时变异、重渲染全部 PDF/PNG、更新全部 hashes，再执行完整 probe：

| 变异 | 独立观察与边界 | 完整 probe |
| --- | --- | --- |
| DIMENSION 图层 off | ezdxf 独立 Frontend 隐藏两个尺寸，产品 PDF 仍绘出两个尺寸 | **0 / passed，错误** |
| DIMENSION 图层 frozen | 独立 Frontend 隐藏两个尺寸，产品 PDF 仍绘出两个尺寸 | **0 / passed，错误** |
| DIMENSION 图层 transparency=1 | 独立 Frontend 的尺寸文字/箭头消失，产品仍绘出 | **0 / passed，错误** |
| 首个 DIMENSION color=2 | 产品 PDF 水平尺寸线/箭头变黄，当前正常尺寸为黑；读回与 probe 接受 | **0 / passed，错误** |
| DIMENSION lineweight=211 | 父级属性变化未拒绝；不夸大当前 renderer 对粗细的表现 | **0 / passed** |
| DIMENSION 图层 true_color=0xffffff | 属性变化未拒绝；独立 Frontend 此例仍显示黑，不能声称已经证明白箭头 | **0 / passed** |
| DIMENSION 图层 color=2 | 图层属性变化未拒绝，列作有效属性覆盖缺口 | **0 / passed** |
| 图层 off + 白 truecolor + DIMENSION BYLAYER | 组合继承状态仍接受 | **0 / passed** |

最强反例为 off/frozen：尺寸图层在 DXF 中关闭/冻结，而产品 PDF 与完整 probe 仍把尺寸当作正常可见。该结论不依赖真实 CAD，也不把 ezdxf 的解释冒充实际 AutoCAD。父级黄色例的产品 PNG 已目视确认；独立 Frontend 对该例仍是黑色，解释差异原样保留。

可复核证据：`display-review.json`、`display-full/layer-off/validation/probe-result.json`、`display-full/layer-frozen/validation/probe-result.json` 及各 case 的整份 candidate/日志；`native-display-review.json`、`visual/native-display-comparison.png`。独立图使用 `Frontend/RenderContext/MatplotlibBackend` 白底黑前景，未替换产品输出。正常三页、反例产品图、独立对照及差异表联系图均已检查。

建议将父实体/图层/ByLayer/ByBlock 的有效可见性、颜色、线型/粗细和受控显示状态纳入独立期望检查，或对本受控格式严格拒绝未批准值；renderer 与 readback 同时修正，并保留噪声与显式默认正例。只增加若干缓存实体字段不能关闭 F04/F05 整类问题。

### [P2] 验收组件依赖传入 digest，未重算当前物理输入输出（F09 后续）

位置：`service/src/heater_drawing/drawing/dwg_adapter.py:141`，输入/输出分支约 172–188 行。**上一轮“保留真实 token 后改运行字典或重绑未执行 DXF”已修复**：每调用独立 token + 私有完整 JSON 摘要表，连未知深层扩展也校验；真实普通 Python helper 正例通过，15 项保留 token 篡改、跨调用 token、未执行输入输出重绑、导入 JSON 均拒绝。版本记录 11 项篡改亦拒绝；物理 descriptor/stdout/stderr 文件改动拒绝。

新增独立试验保留真实运行记录原样，单独把实际 input.dxf 或 output.dxf 的 `10.0` 改成 `11.0`，保持文件大小不变。调用 `_runtime_execution_error(..., require_runtime_provenance=True)`：传原先缓存的 `(path, expected_hash)` 元组时 **返回 None / 接受**；传重新计算的实际 hash 元组时拒绝。原文件和变异字节 `.bin` 已保存，执行后恢复原文件，正例再次通过。两个物理文件的 SHA 由 `820f3716a9560b1dd6d2c3011fe6528c329a5758c2ec7a2669cf98c4a6bfb424` 变为 `5a37e75f76df0da8dd72de0adbfd39cb69d762735662c5118bdfc6f43a01e52e`。

这是“验收时重校当前 input/output”的**组件级限制**：函数比对调用方 digest 与 size，自身不重算输入输出；不能据此声称已绕过正常 capability 全链路，因为外层正常路径会重新计算 artifact hash，导入运行记录仍拒绝，本轮没有任何真实转换 verified 正例。建议在最终校验时直接重算物理文件 hash，或将必须提供新鲜 digest 的前提明确收敛到唯一受信调用边界，并覆盖同尺寸改字节。

证据 `receipt-supplement.json`、`receipt-supplement-final/`、`receipt_supplement.py`。首次补充试验的版本夹具漏写所需产品字符串，未产生最终 JSON；其原始夹具/日志保留于 `receipt-supplement/`。修正后的夹具明确输出 `ODA File Converter FIXTURE ONLY`，实际执行的只是普通 Python，不是 ODA 或转换器。未伪装真实转换批准证据。

## 其余闭环与限制

| 项目 | 本轮处置 |
| --- | --- |
| F01 | 关闭保持：24 页差异表、349 行、2,238 单元格、34,163 可见字形；展示内容/数值映射一致、无越界 |
| F02 | 当前字体对齐与软件再生成关闭保持；真实 CAD 尚待执行 |
| F03 | 引线、尺寸侧别及字形/图框/几何碰撞检查通过 |
| F04/F05 | 指定九项通过，新增 P1 使整类仍未关闭 |
| F06 | 真实 CAD 与项目授权 DWG 转换仍 pending；本轮没有人工或真实转换正例 |
| F07 | 原始候选/模板及既有材料字节不变，双端保护通过 |
| F08 | 三页 C02 均通过 |
| F09 | 原记录篡改漏洞关闭；新增物理文件重校限制见 P2 |
| 黄色/黑色图框 | 六份页面表示各 21 段颜色/端点匹配通过，两类完整负例拒绝 |
| B01 | 当前源码/报告/Git blob 绑定有效，十二反例阻断；历史唯一认可事实未替换 |

差异表源线段 55/55/65，各匹配 4、未匹配 51/51/61；候选各 21，未匹配各 17，实际展示集合一致。每页候选文字 41 项；源文字语义保持 unknown/approval，不从轮廓推定文字准确。三张候选、源图联系表、覆盖全部 24 页的六张差异联系图及第 1/12/24 页完整图已目视检查。

实际字体 OTF `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`，PostScript `NotoSansCJKsc-Regular`；源 TTC `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a` 的 face 2。独立读 name 表及安装包 copyright，SIL OFL 1.1；未增加字体二进制或采用许可不明 SHX。原 TEXT/缓存 MTEXT、MTextExplode 后实体、再生成均锁定同一实际字体；129 实体、876 字形、12 箭头最大误差分别 **0.0000170093 / 0.0000172347 mm**，再生成误差 **0 mm**、碰撞 **0**，单页与合并对应页一致。

六个原生尺寸各再生成两次、保存重开再生成，完整缓存语义稳定；改定义点宽向 +5 / 长向 +7 后测量和缓存正确更新为 **35/57、30/32、105/307**，保存重开稳定。仅为 ezdxf 软件验证，未声称改轮廓自动关联更新或实际 CAD REGEN 合格。`signature-inputs/` 字节副本签名相同、几何平移签名不同，是软件签名控制，不是 DXF–DWG–DXF 往返材料。

普通 helper 的 exit 7 拒绝，stdout/stderr 各 6001 B 完整保存；0.15 s timeout 后子进程 sentinel 未出现。缺失/stale/junk/header/低熵/高熵伪 DWG 全拒绝；默认 capability 为 not_configured。Windows 改名 Python 仅复制和核对 Authenticode，未执行；Linux vendor trust 拒绝。真实输入、倒置版本时间、导入记录、错误内层/外层摘要等保持 fail closed。

B01 当前 summary SHA `863881a84daedd610eb6e57e8dd22276acd47010b896a7f3b9c185825380d6ac`、binding SHA `b152782a963e32c9cc8581e59cf067d2705e2d3daa61141b8a1ef5d91396303e`；执行源码 HEAD `f3206f05a16fa29cebfb4810e4b33ea0f64fbd67`、binding commit `7354426dfd633d7b8b13f543ac1e3457d963b062`，已独立核查，不以当前文档 HEAD 代换。执行器归档第五报告 SHA `649cf7467d617427f72690b955324d032cf8957afc17d96780cb1265c2a5a9b5`；历史认可 B01-fix2-r2 SHA `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0` 未改写。

`format-profile.json` 尚有历史 fix-5 candidate hash，template-approval 尚有 fix-3 引用；当前均 pending 并保持阻断，不能说成已接受错候选的现成漏洞。未来送人工前必须更新到届时精确候选，绑定具体文件 hash、人员/角色、时间、目标 CAD/版本及打开/再生成/检查动作，授权 DWG 转换与往返也需真实证据。本轮技术闭环条件未满足，故不提供“可直接批准”的人工包。停止于 B02。
