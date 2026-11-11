# B02 第六次修复当前交付报告

日期：2026-11-08

## 结论与范围

本轮只处理第五轮独立复审留下的 P1 F04/F05（尺寸缓存有效显示属性不完整）和 P2 F09（同进程 runtime token 未绑定原始执行内容）。未进入后续 Batch，未重开 F01/F02/F03/F07/F08、颜色、六尺寸再生成或 B01 历史认可。

没有运行 ODA、真实 DWG 转换或真实 CAD，没有借用许可、伪造批准或修改 `docs/reviews/B02.md`、`docs/evidence/B02-rereview-5/` 及既有复审证据。第五次执行报告已按原字节归档为 `docs/reports/archive/B02-fix-5.md`，归档前后 SHA-256 均为 `649cf7467d617427f72690b955324d032cf8957afc17d96780cb1265c2a5a9b5`。

权威 Linux B02 runner 仍为 **blocked**，但技术检查全部通过；仅保留真实 blocker：`human-gate-0` 和 `check-format-gate`。

## 第六次修复

| 发现 | 修复 | 验证 |
|---|---|---|
| P1：缓存签名漏掉可见性、true color、OCS/extrusion、背景、厚度等有效显示属性 | 受控缓存签名统一纳入 common graphical attributes、颜色/true color/transparency、可见性、OCS/extrusion、thickness、变换、MTEXT 背景/方向/行距和 TEXT 控制；未知显式扩展进入严格签名。DIMENSION 本体也校验受控显示缺省 | 完整候选同时变异单页和汇总 DXF。MTEXT/LINE invisible、SOLID true color、MTEXT extrusion/background、LINE thickness 均被 renderer 明确拒绝且 probe 退出 1 |
| P1：renderer、readback、probe 事实可能不一致 | renderer 对受控 profile 不支持的 invisible、true color、transparency、非缺省 OCS/extrusion、thickness、ltscale、MTEXT background fail closed | `0.001 mm` 完整重渲染后退出 1；`3e-14 mm` 和显式缺省完整重渲染后退出 0；P1 向量为 `1,1,1,1,1,1,1,0,0` |
| P2：模块单例 token 可保留后重绑记录 | 每次 helper 返回独立 token；模块私有表将 token 绑定到完整深层规范摘要。每次验收重新校验摘要、record descriptor、stdout/stderr 文件及输入输出绑定 | 原始同进程记录通过；保留 token 后修改 argv、PID、时间、executable、input/output/logs/descriptor 的深层字段及重绑未执行 DXF 全部拒绝；导入 JSON 仍为 unverified |

## 技术证据

- 冻结候选位于 `docs/evidence/B02-fix-6/candidate/`：三页可编辑 R2018 DXF、三份 A4 PDF/PNG、合并 DXF/PDF 和 24 页差异 PDF。
- 五份最终 PDF 已用 Poppler 全部渲染；三页图纸与 24 页差异表逐页目检，无空白、裁切、重叠或缺字。
- Windows 完整回归：175 passed，0 skipped，131.33 s。
- Linux 完整回归：175 passed，0 skipped，91.89 s。
- B02 runner 内：75 项格式失败测试和 175 项完整回归均通过。
- P2 harness 明确为 ordinary Python DXF-copy，`converter_run=false`、`approval_claim=none`，不构成转换、DWG、CAD、许可或批准证据。

## Runner 与边界

| 检查 | 权威结果 |
|---|---|
| Linux 外部源码边界 | before/after 均 passed；`comparison.status=unchanged` |
| B01 impact runner | passed；53 contract + 47 planning，0 skipped；10 checks passed；`dirty_files=[]` |
| B01 当前绑定 | summary SHA-256 `863881a84daedd610eb6e57e8dd22276acd47010b896a7f3b9c185825380d6ac`；历史认可仍是 `B01-fix-2-r2/summary.json` 的 `fc1eaa3f...` |
| B02 runner | blocked；probe、75 format、175 regression、dependency 和三个技术 checks 通过；`dirty_files=[]` |
| B02 blockers | 仅 `human-gate-0: human gate is not approved` 与 `check-format-gate: required environment unavailable (exit 2)` |
| DWG capability | `not_configured`、`conversion_run=false`、`approval_claim=none` |

最终源码契约 SHA-256 为 `e96fdcc246ba0cc63bcd9eea677e56d7966b1673ab13aa480baa270a636ed0c1`。权威 Linux 边界提交为 `f3206f05a16fa29cebfb4810e4b33ea0f64fbd67`，B01 绑定提交为 `7354426dfd633d7b8b13f543ac1e3457d963b062`，B02 runner 证据提交为 `edeeee41f6b343eacdfad370ceca5b0909f97087`。

## 当前精确哈希

| 文件 | SHA-256 |
|---|---|
| `candidate/candidate-manifest.json` | `b87e9dfa1acdc7ae3cc2824f52e0eeccb11c3146f776c79e4e318b59f328fc8a` |
| `candidate/heater-sample.dxf` | `6d83f17e8c8007cefc0594a33f0ec78951469e46d15e763fe959e100ed4b672a` |
| `candidate/heater-sample.pdf` | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| `candidate/reference-difference.pdf` | `624d8547ace7ed6e9db35adc6b96c6d62a46c9f8b0a511493a9f46408c6859b5` |
| `validation/probe-result.json` | `eaeea1670f784639f74510a7a5028f9ae910393df81a78a30a6577ad8363807d` |
| `full-probe-display-results.json` | `61bf0b1c30d6a23669782aeebb984ae1fb78987b8f33a4a33469f2535716123b` |
| `runtime-record-results.json` | `5abedfc5b199d015509f5930aee15ca2538097bd9892d69df799c0cc3fbbfd5d` |
| `b01-runner/summary.json` | `863881a84daedd610eb6e57e8dd22276acd47010b896a7f3b9c185825380d6ac` |
| `b01-acceptance.json` | `b152782a963e32c9cc8581e59cf067d2705e2d3daa61141b8a1ef5d91396303e` |
| `b02-runner/summary.json` | `c58a3d85519faee66cc0286b6bf2cbfaa3c1e652b87d7455624bfd2aed0a828e` |
| `human-approval.json` | `a34df1b0a076d5e58ae1d4a0271f8d6b240bc6a1cc4612954134e5c20b7cc40b` |
| `dwg/capability.json` | `29504ef1a45653b17c97bcc6cd522212862373ab47b7e79ab5089655dc17cef5` |
| `gate-result.json` | `286c5aee9c86785bb14f5587e8a4b3feb9234a379d8f6a0dac145efe3fa00cf9` |

## 未执行与后续约束

- 未由具名工程师在 AutoCAD 2018 中对精确 fix-6 候选执行打开、编辑、更新尺寸、保存和重开。
- 未执行真实 DXF-DWG-DXF 正反转，未配置或调用 converter，没有真实 DWG 输出。
- 未获得模板、字体、颜色、引线、差异、尺寸行为或 DWG 首发范围批准。
- `docs/reviews/B02.md` 仍是第五轮独立复审 **FAIL**；本报告不能覆盖它，也未启动第六轮独立复审。
- 在人工门槛、DWG 范围决定和后续独立复审完成前，B02 保持 blocked，不得进入 B04。
