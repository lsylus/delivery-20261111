# B02 第九次修复当前交付报告

日期：2026-11-08

## 结论与范围

本轮只处理第八轮独立复审的两个发现：原生 DIMENSION 再生成仍可从 `HEATER_DIM` 或实体 override 的 `dimltype`、`dimltex1`、`dimltex2` 引入 profile 外线型；fix-8 待签记录的模板子绑定、scope 与动作键又彼此分裂。未启动后续 Batch，未重开已通过的历史项。

第九轮已把实际 DIMSTYLE、每个 DIMENSION override 及解析后的 LTYPE 定义纳入共享签名和校验，renderer、readback、重建缓存与 page consistency 使用同一事实。审批 scope 和 DXF/DWG 动作键改由 `scripts/b02_approval_contract.json` 单一提供；待签生成器从最终 probe 与模板字节计算候选、模板、layout、font 和全产物绑定。人员、角色、时间、结论仍为空，十项 CAD 动作仍为 false，没有把测试记录冒充批准。

权威 Linux B02 runner 为 **blocked**，但全部技术检查通过；blocker 仅 `human-gate-0` 与 `check-format-gate`。当前 `docs/reviews/B02.md` 仍是第八轮独立复审 **FAIL**，第九轮尚未启动独立复审。没有运行真实 CAD、DWG 转换或工程批准。

第八次报告已按原字节归档为 `docs/reports/archive/B02-fix-8.md`，归档 SHA-256 为 `9550b0d801453860f9dda54f2ceceedf408669a5599645f8857bb89b97378d6c`。

## 修复与验证

| 发现 | 修复 | 验证 |
|---|---|---|
| DIMSTYLE/override 三个线型来源未受控，旧缓存可掩盖下一次 REGEN 后的虚线 | 共享策略规范化省略默认与显式 `Continuous`，绑定实际来源和规范 LTYPE 定义；profile 外来源在 renderer/readback 前置拒绝；预期缓存按已验证的实际来源重建 | DIMSTYLE 与 override 各 3 个异常来源在 renderer、readback、完整候选 probe、`render()`-保存-重开四条路径全部拒绝 |
| 正例可能被过度收紧 | 仅控制实际可达来源，不扩大到未引用表项；连续线定义仍规范浮点噪声 | 省略默认、显式 DIMSTYLE `Continuous`、显式 override `Continuous`、`3e-14` 噪声、未引用附加 LTYPE 五正例均在再生成保存重开后通过 |
| 待签记录模板 hash 过期，scope 5 项与 validator 4 项分裂，10 个动作与 validator 8 个动作分裂 | 单一 JSON 契约定义 5 项 scope 和含更新尺寸、REGEN、保存、关闭、重开的 10 项动作；gate 即使在 pending 状态也校验候选/模板/font/layout/action 形状 | 规划 CLI 决策矩阵通过；错误模板 hash 与缺少 `regen` 的正向批准形状均被拒绝；当前 gate 只报告真实未决项 |

独立审计位于 `docs/evidence/B02-fix-9/dimension-linetype-audit.json`，明确记录 `converter_run=false`、`actual_cad=false`、`approval_claim=none`。正常候选 probe 为 passed，`candidate_immutable=true`、`template_immutable=true`。

## Runner 与边界

| 检查 | 权威结果 |
|---|---|
| Windows 全回归 | 206 passed，0 skipped，153.00 s |
| Linux 外部边界 | before/after 均 passed；`comparison.status=unchanged`、0 changes |
| 最终源码契约 | `c230951d42c5dc36b926ec004243058e0c848d9b877932dd9c183e1e52de1da8` |
| B01 impact runner | passed；53 contract + 47 planning，0 skipped；全部内建检查通过；`dirty_files=[]` |
| B01 runner HEAD | `4e6415754ea6767ee4ef35d2594c9a10acf601c7` |
| B02 runner | blocked；正常 probe、106 format、206 regression 及三个技术 checks 通过；`dirty_files=[]` |
| B02 runner HEAD | `bc9c54921be053e6792ecae08d17905db918a92d` |
| B02 blockers | `human-gate-0: human gate is not approved`；`check-format-gate: required environment unavailable (exit 2)` |
| DWG capability | `not_configured`、`conversion_run=false`、`approval_claim=none` |

## 当前精确哈希

| 文件 | SHA-256 |
|---|---|
| `templates/heater-a4-v1/manifest.json` | `2547022cfa542cc29d3fe729ba53ef2d0fdb43800f54aa143bc2a895f84467f4` |
| `candidate/candidate-manifest.json` | `c6753008957f5359e529e67f77fca884b344fc3abd87ce344ed8d6bd91574d0d` |
| `candidate/heater-sample.dxf` | `ea7a52a54b238160806171df40e2ca63897c8d54f4f90783fc0e8a5cf53c39d5` |
| `candidate/heater-sample.pdf` | `2a651758157f468179f58a432439b2128ae85968ee3f41de69c2644556d8a61f` |
| `candidate/reference-difference.pdf` | `d5b29ddacc22976fe446f68219ed0bf7a5b75e8133c578e8bb40258a73ac3714` |
| `validation/probe-result.json` | `9e1e97c402d29b2b57bd679147f546d9f5a1529da779b3a19f494128452a5588` |
| `windows-validation/probe-result.json` | `92689a52dad02aae95f775c7b2337e13e650c620de45853bab5176b1fd6004ab` |
| `dimension-linetype-audit.json` | `d5df3ad7854cb703ea84736eae1a7bbfa7f60366b033c33950353d805acc2eaa` |
| `b01-boundary-before.json` | `957ef2b3c55706cc5105a385062ceb91949bdb2ac5c846a62c8a5ec72af37c63` |
| `b01-boundary-after.json` | `70960f1123c729f5ce3ae3570861a25b44ec85854f71518472f74167540b1bbe` |
| `b01-runner/summary.json` | `858af6924427e585606f6abd3c159468ddbc5db7d06e47fe7aa6790cb1cfe84e` |
| `b01-acceptance.json` | `99e8fa4a44a5b647d4f73feb5a48d83429817b42f6e48daa666165818f5754d2` |
| `b02-runner/summary.json` | `0edacb8331d3bfafdce282b4931ed3c8409c0502a9d85373927016876a7c8f31` |
| `human-approval.json` | `a8f921dcff1fe1813b5149093b3a399a4f0099bf44c67dc68f0c0f31babeef17` |
| `dwg/capability.json` | `3ed27aba9f12dcec927a0da646e2143b8105dd15000098652a265163aaeb3c56` |
| `gate-result.json` | `80f9bb80f729c80be95a5f645fdc2f001dbe05cf2c58a4011436d70e28f79adc` |

## 未执行与后续约束

- 未由具名工程师在 AutoCAD 2018 中对精确 fix-9 候选执行打开、编辑、显式更新尺寸、REGEN、保存、关闭和重开。
- 未执行真实 DXF-DWG-DXF 正反转，未配置或调用 converter，没有真实 DWG 输出。
- 未获得模板、黄色框、Noto Sans CJK SC 替代、5/10/10 mm 引线、测量差异、原生尺寸行为或 DWG 首发范围批准。
- 本报告不能覆盖第八轮独立复审 FAIL；新独立复审只能审阅本报告、fix-9 当前证据与上述源码契约。
- 在人工门槛、DWG 范围决定和后续独立复审完成前，B02 保持 blocked，不得进入 B04。
