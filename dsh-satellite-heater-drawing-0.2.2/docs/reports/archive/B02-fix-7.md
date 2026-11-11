# B02 第七次修复当前交付报告

日期：2026-11-08

## 结论与范围

本轮只处理第六轮独立复审留下的 P1（父 DIMENSION、受控图层及缓存嵌套 BYLAYER/BYBLOCK 有效显示链）和 P2（runtime 校验未自行重算当前物理输入输出 hash），并刷新候选特定的待签记录。未进入后续 Batch，未重开已关闭发现、黄色框、六尺寸再生成、时间戳或 B01 历史闭环。

没有运行 ODA、真实 DWG 转换或真实 CAD，没有借用许可、伪造批准或修改 `docs/reviews/B02.md`、`docs/orchestration/` 及既有复审证据。第六次执行报告已按原字节归档为 `docs/reports/archive/B02-fix-6.md`，归档前后 SHA-256 均为 `98870e4dae5f3c759d41c3c6b529dd2b9883c76144160dd4dcc70f8210d44677`。

权威 Linux B02 runner 为 **blocked**，但所有技术检查均通过；最终 blocker 仅 `human-gate-0` 与 `check-format-gate`。当前 `docs/reviews/B02.md` 仍是第六轮独立复审 **FAIL**，第七轮尚未启动独立复审。

## 第七次修复

| 发现 | 修复 | 验证 |
|---|---|---|
| P1：父 DIMENSION 或受控图层属性可改变尺寸有效显示，而缓存局部签名仍通过 | 新增共享显示策略；严格验证受控图层 off/frozen/locked、ACI/true color、transparency、linetype、lineweight，以及父 DIMENSION、LINE/MTEXT/INSERT 缓存和嵌套 SOLID 的 BYLAYER/BYBLOCK 继承；renderer 与 readback 共用该策略 | 正常完整候选通过；15 个完整候选变异均被 renderer 拒绝且 probe 精确退出 1，覆盖父实体、图层、缓存和组合继承 |
| P2：调用方可保留旧 digest，物理文件同尺寸换字节后仍可能通过 | `_runtime_execution_error` 每次自行重算当前物理 input/output SHA-256，并同时核对当前、调用方与封存记录摘要 | input/output 的同尺寸改字节、删除、替换全部拒绝；每次恢复后通过；`all_physical_mutations_rejected=true`、最终 positive error 为 null |
| 候选待签记录仍绑定旧轮次 | `format-profile`、模板审定输入、人工门和 registry 全部绑定 fix-7 精确候选与 hash | actor、role、time、conclusion 均为 null，AutoCAD 2018 动作均为 false，`approval_claim=none`，未冒签 |

## 技术证据

- 冻结候选位于 `docs/evidence/B02-fix-7/candidate/`：三页可编辑 R2018 DXF、三份 A4 PDF/PNG、三页汇总 DXF/PDF 和 24 页差异 PDF。
- 五份最终 PDF 共 30 页已用 Poppler 全页渲染并逐页目检；无空白、裁切、重叠、黑块、缺页或不可读内容。这是技术视觉 QA，不是工程批准或目标 CAD 证据。
- Windows 完整回归：191 passed，0 skipped，142.16 s；Linux 完整回归：191 passed，0 skipped，100.87 s。
- 最终 B02 runner 内：91 项格式失败测试和 191 项完整回归均通过；DXF/PDF probe 退出 0。
- 独立 ezdxf Frontend 对照退出 0，并明确标记为软件解释，不构成真实 CAD、转换、许可或批准证据。
- P2 harness 是 ordinary Python DXF-copy，`converter_run=false`、`approval_claim=none`。

## Runner、边界与外部变化

| 检查 | 权威结果 |
|---|---|
| 注册 Linux 外部边界 | `b01-boundary-before.json` / `b01-boundary-after.json` 均 passed；`comparison.status=unchanged`、0 changes；符合 C07 对完整、同 source contract、baseline hash 匹配及有效时限的要求 |
| 独立 post-run 观察 | 从较早 baseline 重算后记录 `dsh-satellite-drawings` 工作树 state 从 `386135b6...` 变为 `c19edb70...`；`changes_observed`、`attribution=unknown_external`；未回退、未归因于本项目，也未覆盖注册边界 |
| B01 impact runner | passed；53 contract + 47 planning，0 skipped；10 checks passed；`dirty_files=[]` |
| B01 当前绑定 | summary SHA-256 `14da75e922eae952032639d49211ecf600a696fbb9ef7a2ffdb765a7db6f0e43`；acceptance SHA-256 `3cec8250f337b5d27cba30af4af6e40a689e72f58cb5dcdea6cdbf221451e113` |
| B02 runner | blocked；dependency、probe、91 format、191 regression 和三个技术 checks 通过；`dirty_files=[]` |
| B02 blockers | 仅 `human-gate-0: human gate is not approved` 与 `check-format-gate: required environment unavailable (exit 2)` |
| DWG capability | `not_configured`、`conversion_run=false`、`approval_claim=none`；没有 converter 或真实 DWG 输出 |

最终源码契约 SHA-256 为 `f532dc2529653cae02ad0bcc01996cdbf801495f97e9af3154ca672866c5b1b7`。Windows 源码提交为 `a2988ef`、`4e2f2a3`；Linux 源码提交为 `0684594`、`34b5f1c`。最终 clean B01 运行 HEAD 为 `725982c67c4ab690f90245beea3afd62e1f306cd`，最终 clean B02 运行 HEAD 为 `5c3bbd7e1343f93187c7c77fdd974714e11f6052`。

## 当前精确哈希

| 文件 | SHA-256 |
|---|---|
| `candidate/candidate-manifest.json` | `216d18c4fd9d29e0a7daaf2966830c812f9be7f3aedfe369a70fcfb657ed8c74` |
| `candidate/heater-sample.dxf` | `bcde27d09356a103e85714a44a6a7f58db867b6d5c3914aa4eec332f5e336446` |
| `candidate/heater-sample.pdf` | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| `candidate/reference-difference.pdf` | `8410a92af363d4aacdbdd205f160b75fb35e534c2161478291e213154fc452a5` |
| `validation/probe-result.json` | `8e179dbb1f6b69e3596df243e3f9e68b3e7da26bd79573844d16ea6be70116ca` |
| `display-mutation-results.json` | `7b1350aac1eec853e86de16fc107072d4808adadc33164edaffcf895c97d6bce` |
| `runtime-hash-results.json` | `faf05ab20b3e5ee14407b31c71701972d3d54e3eca190c5cf9ccba9fa1b78a54` |
| `frontend-display-results.json` | `7f02f902f56dd622b30ebb92bea71e3a217a8a63d12ede03990d3feea7fdff0b` |
| `visual-review.json` | `cff4d913f0fa99f4a91f76cc8e8d94f183e587db2572ff8a62b96641b452b110` |
| `b01-boundary-before.json` | `7c3891ec2393c1d47f0176532b1a7f73ac97a74c6f63c99588d6e733487c9b68` |
| `b01-boundary-after.json` | `cac42daa6604afa7507575fc56b2e92b257a52d87bbe4cd5da22fd37c2250de4` |
| `b01-boundary-post-run-observation.json` | `3e5ed8edee28586658c379b5cb53e649ee629453f0aab2ca0ba92bbe52b99d76` |
| `b01-runner/summary.json` | `14da75e922eae952032639d49211ecf600a696fbb9ef7a2ffdb765a7db6f0e43` |
| `b01-acceptance.json` | `3cec8250f337b5d27cba30af4af6e40a689e72f58cb5dcdea6cdbf221451e113` |
| `b02-runner/summary.json` | `5106b715602a2d343313970607788f9c3af98f91660583bd3959be8d99a8c916` |
| `human-approval.json` | `fa2c938ef95c01be7f05e74b3d68e5b9522430b081cea1eda4bbd9427f2abf45` |
| `dwg/capability.json` | `df1bbdd608f9c5eb584e96bc91136f1c4ad99e01ba4f601ce843164c42532370` |
| `gate-result.json` | `27da94fee4feb9a0362199a3a61018b8ee2618ba1c4fb968bc010068ff4b6f88` |

## 未执行与后续约束

- 未由具名工程师在 AutoCAD 2018 中对精确 fix-7 候选执行打开、编辑、显式更新尺寸/REGEN、保存、关闭和重开。
- 未执行真实 DXF-DWG-DXF 正反转，未配置或调用 converter，没有真实 DWG 输出。
- 未获得模板、Noto Sans CJK SC 替代、5/10/10 mm 引线、差异、尺寸行为或 DWG 首发范围批准。
- 本报告不能覆盖第六轮独立复审 FAIL；新独立复审只能审阅本报告、fix-7 当前证据和上述源码契约。
- 在人工门槛、DWG 范围决定和后续独立复审完成前，B02 保持 blocked，不得进入 B04。
