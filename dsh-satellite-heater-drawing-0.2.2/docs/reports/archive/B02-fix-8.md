# B02 第八次修复当前交付报告

日期：2026-11-08

## 结论与范围

本轮只处理第七轮独立复审留下的 P1：受控图层虽然引用名为 `Continuous` 的 LTYPE，但该表项定义可被改成虚线或复杂线型，导致 DXF 与 PDF 显示不一致，而 renderer、readback 和完整 probe 仍误放行。未进入后续 Batch，未重开已关闭的父 DIMENSION、图层、缓存继承、runtime 物理文件、黄色框、尺寸再生成、C07 或 B01 历史闭环。

没有运行 ODA、真实 DWG 转换或真实 CAD，没有借用许可、伪造批准或修改 `docs/reviews/B02.md`、`docs/orchestration/` 及既有复审证据。第七次执行报告已按原字节归档为 `docs/reports/archive/B02-fix-7.md`，归档前后 SHA-256 均为 `439a7c5e31f6163c7551ec57c207fe33bc171695b11251a534409ff74251bc13`。

权威 Linux B02 runner 为 **blocked**，但所有技术检查均通过；最终 blocker 仅 `human-gate-0` 与 `check-format-gate`。当前 `docs/reviews/B02.md` 仍是第七轮独立复审 **FAIL**，第八轮尚未启动独立复审。

## 第八次修复

| 发现 | 修复 | 验证 |
|---|---|---|
| `Continuous` 名称不变时，LTYPE 定义可漂移为 dash/gap 或复杂线型 | 共享显示策略记录并校验被受控图层引用的 LTYPE 定义：名称、复杂标志、编译 pattern 和原始 pattern tags；浮点值统一到 12 位并规范零值 | coarse dashed、scaled dashed、complex 三反例均被 renderer、单页/汇总 readback 和完整 probe 拒绝；显式默认与 `3e-14` 浮点噪声两个正例完整重渲染后通过 |
| 最初冻结候选早于 fix-8 模板待签路径更新，最终 runner 检出 template binding mismatch | 保留失败 runner 诊断；按最终模板 manifest 重新生成候选、重跑正常 probe 和全部五组完整候选，不手改 candidate hash | 最终 candidate 绑定模板 manifest `f0cb0d964408284f4ea9e7ae85fe03c2673d52ee8d6cc7d77530b14c380b8193`；Linux/Windows 正常 probe 均通过且候选/模板 immutable |
| 候选专属待签记录需随最终重建刷新 | format decision、模板审定输入、human gate 与 registry 全部绑定 fix-8 最终候选及精确 hash | actor、role、time、conclusion 均为 null，AutoCAD 2018 动作均为 false，`approval_claim=none`，未冒签 |

## 技术证据

- 冻结候选位于 `docs/evidence/B02-fix-8/candidate/`：三页可编辑 R2018 DXF、三份 A4 PDF/PNG、三页汇总 DXF/PDF 和 24 页差异 PDF。
- 最终 `linetype-mutation-results-final.json` 同时记录 `all_negative_definitions_rejected=true` 与 `all_normalized_positive_definitions_passed=true`；harness 明确为 ordinary Python，`converter_run=false`、`actual_cad=false`、`approval_claim=none`。
- Windows 完整回归：198 passed，0 skipped，153.59 s；Windows 正常 probe passed，`candidate_immutable=true`、`template_immutable=true`。
- Linux B02 runner 内：98 项格式失败测试与 198 项完整回归均通过；正常 DXF/PDF probe 退出 0。
- 最终 PNG 与合并 PDF 的内容 hash 沿用第七轮已验技术视觉输出；本轮新增校验针对 DXF LTYPE 定义及 renderer/readback 一致性，不冒充目标 CAD 或工程批准。

## Runner 与边界

| 检查 | 权威结果 |
|---|---|
| Linux 外部边界 | before/after 均 passed；`comparison.status=unchanged`、0 changes；最终源码契约 `ae71328789ba590b5c681a4d376f56e8ed571ef1538182e227080a74e1ae4a7f` |
| B01 impact runner | passed；53 contract + 47 planning，0 skipped；10 checks passed；`dirty_files=[]` |
| B01 当前绑定 | summary SHA-256 `c28201500927ce3eb9dea44325f2f4bcb239bdcd618d96319992aa8b183b8c4c`；acceptance SHA-256 `1fccbd22eb87e6b70e902cb02a04207caba14034e225ca5683f0bfcfff16467a` |
| B02 runner | blocked；dependency、probe、98 format、198 regression 和三个技术 checks 通过；`dirty_files=[]` |
| B02 blockers | 仅 `human-gate-0: human gate is not approved` 与 `check-format-gate: required environment unavailable (exit 2)` |
| DWG capability | `not_configured`、`conversion_run=false`、`approval_claim=none`；没有 converter 或真实 DWG 输出 |

最终 clean Linux B01 运行 HEAD 为 `cb7154e59513157a20fd02569fc8bf13825239ac`，最终 clean Linux B02 运行 HEAD 为 `d69421efd6c6669acba2b6ef9713084cdf6ebd74`。Windows 与 Linux 使用等价但独立的 Git 历史；源码契约 SHA-256 均为 `ae71328789ba590b5c681a4d376f56e8ed571ef1538182e227080a74e1ae4a7f`。

## 当前精确哈希

| 文件 | SHA-256 |
|---|---|
| `candidate/candidate-manifest.json` | `d0eead323cf5ff249da2c20b489d9f1253c4a410890eb3ce0aa5289dcd3df3c4` |
| `candidate/heater-sample.dxf` | `18ad30a35bcb3888de917ebb3d078c13d6f5047911c116d14e1438fe4d44c64e` |
| `candidate/heater-sample.pdf` | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| `candidate/reference-difference.pdf` | `b194c12a653cde88d4a0486aa98029cfc4b839d0abdc8eca90972e20b325f5cb` |
| `validation/probe-result.json` | `2a8cf1c8abc434f7a670abfac597c0e9cd8ba51d8748b53887c36d45c287e36d` |
| `linetype-mutation-results-final.json` | `b75395b25b2c822344bfe2fb4d2ff32be8534367c9484488f9d2776bf37a0881` |
| `b01-boundary-before.json` | `d2e062576bb9cf13f07d5109c34ce3269239716506e25573345e6c57d8fd1c93` |
| `b01-boundary-after.json` | `705829b053ae26f471b836d0bdb6256d1714eebef0567bcdd603c53b67eedd9f` |
| `b01-runner/summary.json` | `c28201500927ce3eb9dea44325f2f4bcb239bdcd618d96319992aa8b183b8c4c` |
| `b01-acceptance.json` | `1fccbd22eb87e6b70e902cb02a04207caba14034e225ca5683f0bfcfff16467a` |
| `b02-runner/summary.json` | `51da1b2e5c8a304dbb972d8c4f1326e09f739ba9da2e27d0732516b777ff78c2` |
| `human-approval.json` | `7a432ffd3d7a6b634a6ccc439ada4b2eec492ee6fffba4cd7ebe55f1a24c0d3b` |
| `dwg/capability.json` | `82fb6e9ba82c862966036d66ac88b5170f1b4471cfae351b0a8eb1714e355bef` |
| `gate-result.json` | `a375b48eaa402f01022491c28c11be9cbf0c2947fb338dcea7003092c6ec1013` |
| `windows-validation/probe-result.json` | `3e54ec8a9698c0e88887f3c14db6dd68f598b38bceb131c72e135f6e7621ce29` |

## 未执行与后续约束

- 未由具名工程师在 AutoCAD 2018 中对精确 fix-8 候选执行打开、编辑、显式更新尺寸/REGEN、保存、关闭和重开。
- 未执行真实 DXF-DWG-DXF 正反转，未配置或调用 converter，没有真实 DWG 输出。
- 未获得模板、Noto Sans CJK SC 替代、5/10/10 mm 引线、差异、尺寸行为或 DWG 首发范围批准。
- 本报告不能覆盖第七轮独立复审 FAIL；新独立复审只能审阅本报告、fix-8 当前证据和上述源码契约。
- 在人工门槛、DWG 范围决定和后续独立复审完成前，B02 保持 blocked，不得进入 B04。
