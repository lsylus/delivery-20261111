# B02 第九轮修复独立复审

结论：**FAIL。上轮的越界尺寸线型来源漏检及待签契约分裂已关闭；仍有一项 P2：明确允许的显式 Continuous 来源在真实重生成后被 renderer／完整 probe 错误拒绝。技术闭环未完成，不能标记“技术闭环可送人工”。** 正常候选及默认 runner 技术项通过；真实目标 CAD、具名工程审批及 DWG 范围决定仍未完成。

仅写本报告、第八轮原字节归档 `docs/reviews/B02-rereview-8.md` 和新证据 `docs/evidence/B02-rereview-9/`。归档 SHA-256：`33a16ec4d0d8afaf8c1610d93377dd6519ccc003b881acb4e5fdb325222439ed`。未改业务、既有测试、执行报告、冻结候选、决定、registry、模板或各自 orchestration。未启动 B03、新聊天或子代理；未运行真实 converter、ODA、DWG 转换或目标 CAD，未借许可、未代签。

## 身份与实际输入

用户交接本地 `52161d6548b268fec981e6ac5ec00c25aab9ee7a`；实际开始为仅追加调度文档的 `bed717bf97c1cd5061d761776f515f3e63c6419a`。远端 `8536daeec8a5f44af084fa6bc8540e5b27fcd441`。两端初始 clean，分支 `codex/b01-foundation`；无适用祖先或子目录 AGENTS。源码契约一致：**`c230951d42c5dc36b926ec004243058e0c848d9b877932dd9c183e1e52de1da8`**。

已核对 plan、B02、C02/C05/C06/C07、R02–R04/R07、project-baseline、progress、B01 报告和独立 PASS、上轮复审、当前报告与决定；检查 display_profile、profile、readback、renderer、probe、adapter、gate、审批 JSON 契约／生成器、registry 及测试差异。本地 `167a2d3..HEAD`、远端 `e71f31b..HEAD` 实现 diff 独立保留。

主新鲜快照 `/tmp/heater-b02-rereview9-dfkpgfis/snapshot`；显示矩阵另用 `/tmp/heater-review9-display-7f8c6hzr/snapshot`。均为当前源码。新反例全部从最终 `B02-fix-9/candidate/` 复制。未用 Windows 早期构建替代 Linux 最终冻结输入，未单凭 executor 审计中的 hash 字段认定来源正确。

| 最终对象 | 独立核对 SHA-256 |
| --- | --- |
| candidate manifest | `c6753008957f5359e529e67f77fca884b344fc3abd87ce344ed8d6bd91574d0d` |
| template manifest | `2547022cfa542cc29d3fe729ba53ef2d0fdb43800f54aa143bc2a895f84467f4` |
| 汇总 DXF | `ea7a52a54b238160806171df40e2ca63897c8d54f4f90783fc0e8a5cf53c39d5` |
| 汇总 PDF | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| reference-difference.pdf | `d5b29ddacc22976fe446f68219ed0bf7a5b75e8133c578e8bb40258a73ac3714` |
| executor 最终 validation | `9e1e97c402d29b2b57bd679147f546d9f5a1529da779b3a19f494128452a5588` |
| executor 最终尺寸审计 | `d5df3ad7854cb703ea84736eae1a7bbfa7f60366b033c33950353d805acc2eaa` |
| 当前 pending human record | `a8f921dcff1fe1813b5149093b3a399a4f0099bf44c67dc68f0c0f31babeef17` |

candidate／human／probe 引用的全部产物 hash 均匹配实际文件；其余最终 runner、boundary、capability、gate、Windows validation、执行报告归档 hash 见 `pending-boundary-review.json`。第八次执行报告归档为 `9550b0d801453860f9dda54f2ceceedf408669a5599645f8857bb89b97378d6c`。原候选、模板与新鲜快照逐文件相等，正常双平台 probe 均为 candidate/template immutable。

## 必须修复：[P2] 显式 Continuous 重生成正例的 readback 与 renderer 不一致

位置：`service/src/heater_drawing/drawing/display_profile.py:94/118/265`、`pdf_renderer.py:219/284`、`readback.py:283/729`、`scripts/probe_formats.py:291`。

来源策略明确允许省略和显式 `Continuous`，readback 按实际 style／override 重建参考缓存。在最终候选副本中这样修改，真实重生成、保存并重新加载后，单页和汇总 readback 都接受：

```python
doc.dimstyles.get('HEATER_DIM').dxf.dimltype = 'Continuous'
for dim in doc.modelspace().query('DIMENSION'):
    dim.render()
doc.saveas(output)
```

另外五例分别修改 `dimltex1`、`dimltex2`，或保留原实体全部 override 后追加三个字段之一为 `Continuous`。新缓存 LINE 为显式 Continuous；独立 ezdxf RenderContext 解析 pattern 为 `[]`，DXF audit 均 **0 errors / 0 fixes**。轮廓、尺寸定义、颜色、实际 Continuous 定义及字体未变。

然而缓存显示策略仍硬性要求 LINE 为 `BYLAYER`（嵌套子实体为 `BYBLOCK`），产品 `render_page()` 抛出 `RenderError: LINE dimension cache BYBLOCK/BYLAYER display binding drift`；完整 probe 的实时重渲染同样失败。

| 独立最终候选副本 | 重生成保存重开后单页／汇总 readback | renderer | 完整 probe |
| --- | --- | --- | --- |
| `positive-style-dimltype` | 接受／接受 | 拒绝 Continuous 缓存 LINE | 1 |
| `positive-style-dimltex1` | 接受／接受 | 同上 | 1 |
| `positive-style-dimltex2` | 接受／接受 | 同上 | 1 |
| `positive-override-dimltype` | 接受／接受 | 同上 | 1 |
| `positive-override-dimltex1` | 接受／接受 | 同上 | 1 |
| `positive-override-dimltex2` | 接受／接受 | 同上 | 1 |
| `positive-omitted-regenerated` 对照 | 接受／接受 | passed | 0 |

又为三个 style 正例建立**三单页与汇总全部一致、所有尺寸均重生成保存重开**的完整输入，排除全局 style 与未修改单页不一致的干扰。三页 readback 均通过，single／aggregate page consistency signature 全部相等，但 renderer 和三个完整 probe 仍失败。见 `dimension-consistency-supplement.json`、`dimension-consistent-cases/`。六个原始实验见 `dimension-source-review.json`、`dimension-source-cases/`。

完整 candidate、刷新后的 manifest、argv/cwd/退出码及 full-probe.log 均保留。renderer 被拒绝的候选保留复制来的 PDF，**未声称成功重建 PDF**；完整 probe 失败发生在自身实时重渲染阶段。`equivalent-page-only-cached` 另记录未重生成缓存的诊断，不作为成功正例，也不据此另报签名漏洞。

executor 新增正向测试及 `dimension-linetype-audit.py` 五 positive 只执行重生成／保存／readback，没有调用产品 renderer 或完整正向 candidate probe；默认 runner 因而没有覆盖这个链路。

必要修复：在现有受控 profile 内统一实际连续线来源、缓存、renderer 和 page signature 的等效处理，使省略默认及已验证定义的显式 Continuous 完整通过 readback→render→probe，同时继续拒绝越界来源、实际虚线定义和错误继承。复核三字段 × style／保留 override 的真实重生成完整正例，保留省略、噪声和未引用表项对照。无需扩展为通用 CAD 线型 renderer。

## 上轮两个发现的关闭情况

**原 P1 来源漏检已关闭。** 六个独立负例分别修改 HEATER_DIM 或保留全部原参数的实体 override 中的三个字段，引用实际虚线 `[10,5,-5]`。原缓存阶段单页／汇总 readback、renderer、完整 probe 均拒绝；真实重生成保存重开后 readback／renderer 也拒绝，独立解析确认实际缓存变为虚线。共享签名覆盖实际来源与定义，预期缓存读取实际 style／override，不再只检查当前画面。

**原 P2 待签绑定／scope／动作分裂已关闭。** 当前 candidate/template/layout/font profile/face 与实际候选／模板匹配，artifact_hashes 等于最终 probe，registry human hash 匹配。五项 scope 和包含尺寸更新／REGEN／保存／关闭／重开的十项动作统一来自 `b02_approval_contract.json`。当前 gate contract errors 为空，仅返回真实人工 pending；人员、角色、时间、结论为空，动作全 false，当前决定路径无旧 fix 候选。

独立 scope、缺 regen、缺 close、额外动作、candidate/template/layout/font profile/face 错 hash 反例均拒绝。内存 test-only 十动作形状诊断不再报动作键冲突，其余缺真人证据错误保留；未写 approved 文件。

在新鲜克隆真实调用待签生成器，JSON 与当前待签 **payload 完全相等**；LF／CRLF 导致字节 hash 不同，规范换行后字节相等。首次过严 byte-equality 诊断 exit 1 日志保留为 `pending-boundary-initial-byte-check.log`；随后按语义及各自真实 hash 验证通过，未改写活跃待签。见 `pending-boundary-review.json`、`generator-pending-output.json` 和生成器日志。

## 独立回归与图面证据

| 检查 | 本轮实际结果 |
| --- | --- |
| 默认原注册 B01 | 0／passed；53 contract + 47 planning、0 skip、10 checks、Node／wheel 均通过 |
| 默认原注册 B02 | 2／blocked；106 format（98.64 s）、206 regression（114.65 s）、0 skip；正常 probe 0，dependency 和三个技术 checks passed；仅 human-gate-0／check-format-gate 阻塞 |
| Windows 独立回归／probe | 206 passed、0 skip、153.33 s；timestamp 用例另五次均 0；最终候选独立 probe 0／passed，candidate/template immutable |
| 显示矩阵 | 54 组件、39 完整 probe；34 负例 exit 1、5 正例 exit 0；正例三页及汇总 PDF 均实际重建 |
| 合理正例 | `3e-14` 缓存几何噪声、普通显式默认、Continuous `[0]`／`[3e-14]`、未引用额外 LTYPE 均通过 |
| 已关闭显示负例 | 粗／细 Continuous 虚线、complex 定义、父 DIMENSION、图层 0、锁定／线宽／plot、缓存、INSERT、嵌套 SOLID 和组合反例均拒绝；九项指定结果 `1,1,1,1,1,1,1,0,0` |
| 旧语义／PDF 负例 | 24 个 DXF 异常拒绝；错误单页、单页横移、仅汇总第二页横移三个完整 probe 均 1；黄色改黑和仅汇总改黑均拒绝 |
| 真实 CLI fixture | 六项实际 check_format_gate／verify_batch 子进程退出 `0,2,1,1,1,0`；只在明确 pytest fixture 临时目录，不是活跃批准 |
| B01 依赖／路径 | 原注册 report／binding 正例通过，12 个删除／伪造／重绑／时效／hash 负例阻断；旧 fix-3 probe 中毒不影响当前 built-in；路径形状反例拒绝 |
| runtime provenance | 普通 Python helper 与恢复正例通过；retained-token 深层／导入／跨调用、版本记录、descriptor/stdout/stderr、输入输出同尺寸改写／删除／原子替换／目录替换均拒绝；未执行 converter |
| 字形／箭头／尺寸 | 129 文字实体、876 glyph、12 SOLID；最大 glyph 边误差 0.0000170093 mm，箭头 0.0000172347 mm；正常 6 尺寸重复重生成保存重开稳定，定义点 +5/+7 mm 后测量／文字正确；再生成 glyph 误差 0，碰撞 0 |
| 字体 | 实际展开及重生成均为同一 NotoSansCJKsc-Regular，OTF SHA `e67a2b986195ba174259130d5d69a09e25cabfe5668fd3e4b6ec031d0a6ae322`；核对 TTC face 2／OTF／系统包许可，未用 fallback 测量 |
| C02／颜色／差异 | 三 DrawingPage 通过公开结构及语义入口；单页及汇总各页 21 段框线端点／颜色对应；24 页差异表 349 行、2238 cells、34163 可见 glyph 检查通过 |

已目视检查三张完整候选、原三页 contact sheet 及差异表全部 24 页的六张 contact sheet。中文字、双引线、尺寸箭头、黄色框和标题栏可辨，无所测碰撞。源图线位／字段重排和字体替代仍待工程批准，第二页标审按 Excel 为“郑玲”。这些软件测量不构成 AutoCAD 编辑验收。

主命令在 `results.json`、`b01-current/`、`b02-current/`；影响验证在 `impact-results.json`；综合事实在 `review-facts.json`。共归档 **61 个完整变异 probe 输入**：39 显示、5 颜色／PDF、14 来源实验和 3 三页一致补充正例。manifest 的每个 artifact hash 均核对，renderer 拒绝者明确未成功重建 PDF；详见 `probe-candidate-archive.json`。

独立 B02 dirty_files 只记录前序生成的 `?? docs/evidence/B02-rereview9-b01-current/`，如实保留；它位于隔离快照且无源码修改。executor 最终两个 runner 仍 dirty_files=[]，B01 HEAD `4e6415754ea6767ee4ef35d2594c9a10acf601c7`、B02 HEAD `bc9c54921be053e6792ecae08d17905db918a92d`。历史独立认可 B01 summary SHA 保持 `fc1eaa3f3159505dac5e4e7c9dc23613fdb70d9b56ece719fbb67789861b67d0`。

## C07、保护与停点

实际读取 registry 当前 fix-9 before／after，核对完整 shape、当前源码、登记 baseline、稳定 hash、24 小时时效并重算：passed／unchanged。两文件 hash 为 `957ef2b3c55706cc5105a385062ceb91949bdb2ac5c846a62c8a5ec72af37c63`、`70960f1123c729f5ce3ae3570861a25b44ec85854f71518472f74167540b1bbe`。本轮另真实采样 before／after 并通过原严格 validator，valid／unchanged；均只解释各自采样窗口。

历史额外 observation `B02-fix-7/b01-boundary-post-run-observation.json`，SHA `3e5ed8edee28586658c379b5cb53e649ee629453f0aab2ca0ba92bbe52b99d76`，与恢复 baseline 重算仍为 changes_observed/unknown_external，对应历史源码 `f532dc2529653cae02ad0bcc01996cdbf801495f97e9af3154ca672866c5b1b7`。未重绑到 fix-9，未要求整个期间外部项目永远不变，未写入或回滚外部项目。

两端分别逐字节保护本地 **5580**、远端 **5572** 个原文件，source entries 相同。原差异为本地九个旧日志／runtime 记录、远端根 .gitattributes 和各自 orchestration state/events，均保留。见 `local-protection-final.json`、`remote-protection-final.json`、`source-mirror.json`。evidence index 绑定报告、原字节归档及全部新证据，排除自身和随后单独提交的 Git handoff；双端各自提交，仅暂存允许路径，核对工作文件／Git blob SHA、diff --check 及 clean。实际双端交接见 `git-handoff.json`。

当前必须修复项只有上述 P2。修复后仍需真人在 AutoCAD 2018 打开精确冻结 DXF，编辑轮廓／文字／原生尺寸，显式更新尺寸、REGEN、保存、关闭、重开，核对单位／字体／尺寸并记录人员角色时间、输入输出 hash、结构化动作及截图；另审定黄色框／锚点、SC 替代、5/10/10 mm 引线和差异表。DWG 仍未配置、未运行、未批准；延期保持基线或升级首发范围需真人决定，升级再满足本项目授权、真实正反转及确切 DWG 的目标 CAD 验收。

**本次停在 B02。正常样件 passed、fixture PASS 或本报告均不替代技术修复／真人批准，不进入 B04。**
