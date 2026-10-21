# 文件和命令

Python 3.10+，仅标准库。用 PowerShell 调用 `python scripts/arena.py --help`。所有命令由协调代理运行，脚本不启动 Codex、不评估内容、不联网。生成与评估由 SKILL.md 指定的独立代理完成。

```text
DATA_ROOT/
  registry.json                 可复用候选索引
  history.jsonl                 真实运行历史，仅协调代理追加
  tmp/                          下载、临时脚本、自测输出
  runs/RUN_ID/
    task.md / protocol.json / rubric.json / discovery.md
    inputs/                     共同输入
    snapshots/                  完整 skill 快照和逐文件哈希
    variants/ID/                每个生成者的完整原件、来源和执行记录
    judge-packet/A/              供评估者查看的匿名原件
    mapping.json                解盲映射，评估者不可读
    evaluation/                 judge.json、verification.md、order-check.md
    report.html / report.md / ranking.json
    interaction.json             会话分步提问参数、真实名称及候选映射
    feedback/EVENT_ID.json        每次用户选择与操作要求
    state.json                   本轮已认可方案索引
    lineage.json                 子轮的来源、操作和分支文件哈希
    handoffs/VARIANT_ID/          协调者准备的各分支专属接续材料
```

示例命令（替换路径与 ID）：

```powershell
python scripts/arena.py init data
python scripts/arena.py register data data/tmp/candidate.json
python scripts/arena.py find data "论文规划 reinforcement-learning"
python scripts/arena.py new-run data 20261020-paper-plan
python scripts/arena.py snapshot data/runs/20261020-paper-plan candidate-a C:/path/to/skill
python scripts/arena.py packet data/runs/20261020-paper-plan data/tmp/variants.json
python scripts/arena.py report data/runs/20261020-paper-plan
python scripts/arena.py remember data data/tmp/history-record.json
```

candidate.json 必备：id、name、source（仓库或 SKILL.md 可访问地址）、version（commit/tag，无法获取则 unknown）、tags（任务类型/领域/交付物）、local_path、license。可附 dependency、fit_reason、limitations、last_run。register 更新索引，不覆盖旧运行快照。相对路径以调用工作目录解析；建议使用绝对路径。

variants.json 是数组，例如 `[{"id":"candidate-a","artifacts":["answer.md","sources.md"]}]`。必须包含所有参赛项；失败项也建目录并提供 failure.md。不要把 execution.json、自评分或身份说明放进评估包。原件包含身份时手工创建匿名副本并记录改动，禁止改动实质内容。packet 会随机排列且拒绝覆盖已存在评估包。

为清晰展示与候选调整，manifest 每项应另附 `display_name`（真实 skill 名称，同名时附结果短标题）、`skill_id`、`kind`（skill 或 baseline）。这些字段只进入包外 mapping.json，不暴露给评估代理。普通提示词必须标为 baseline，不只依赖其文件夹名称。

protocol.json 初始为 draft；派发前填写统一 Codex 模型、网络策略及任务约束，设为 frozen。equal_budget 固定为 false；user_limits 仅记录用户主动提出的总限制，没有则为 null，不要求用户填写。没有附件时 inputs 可为空。rubric.json 除 weights、tie_threshold 外应加入 anchors、hard_conditions；评估者依据这些字段判断，脚本仅校验算术与数据完整性。

history-record.json 必备 run_id、task_tags、skill_versions、environment、status、report_path、synthetic=false。应附 ranking、failure_reasons、user_feedback、limitations；禁止把演示测试当作实测。find 是简单大小写不敏感检索，语义相似性由协调代理复核。

不得自动清理 runs、registry 或 history；临时文件清理只限确认位于 DATA_ROOT/tmp 的路径。第三方快照、用户输入、运行报告默认不提交 Git。发布源码前检查凭据和私人路径，保留 .gitignore。脚本的路径检查不提供安全沙箱；子代理共享文件系统。

## 记录选择与创建后续轮次

用户只说自然语言；下面的 JSON 和命令由协调者准备，不能要求用户填写。先从父轮 mapping.json 把“方案 A”解析成真实 variant ID，不能按排名猜测。

```json
{"mode":"select","variants":["candidate-a","candidate-c"],"user_message":"先保留 A、C"}
```

```powershell
python scripts/arena.py feedback data parent-run data/tmp/selection.json
python scripts/arena.py followup data parent-run next-run data/tmp/request.json
```

request.json 的 mode 为 refine / redo / continue；variants 为父轮真实 ID 数组；instruction 为修改要求或下一项任务；user_message 保存用户原话。示例：

```json
{"mode":"continue","variants":["candidate-a","candidate-c"],"instruction":"根据各自调研设计实验","user_message":"满意 A、C，接着做：根据各自的调研设计实验。"}
```

- select 只记录选择，不新建执行；continue 未传 variants 时读取该父轮 state.json 的已选项，没有选择则报错。
- redo 支持 `"variants":"all"`，展开父轮实际参赛项（包含基线）；“全部 skill”由协调者解析为排除基线的具体数组。refine/continue 需要非空 instruction；redo 可沿用原要求。
- followup 会记录父轮反馈，创建独立子轮及 lineage.json。refine/continue 记录各分支原件路径及 SHA256，redo 不继承旧答案。它不会复制原件、启动代理或自动寻找 skill；handoffs、输入和快照由协调者按 continuation.md 准备。默认协议仍为 draft，完成准备后才冻结与派发。
- 新一轮只记录父轮所选 variant ID，实际 skill/版本从父轮 execution.json、sources.md、快照清单核对，在 handoff 中明确保存。variant ID 不一定等于 skill ID；基线无 skill，继续使用通用能力。
- 同一反馈事件不可因记录工具重试而重复提交；先查看 feedback 和 state。followup 拒绝覆盖已有子轮，若中途失败，检查已有子轮与事件后补完准备，不能盲目重复执行。
- 子轮生成不代表用户认可它。未再次选择时，以最近明确认可的祖先轮次为选择来源，协调者沿 lineage 查找对应 state；显式方案指代则以用户指定轮次为准。无关任务不自动沿用此选择。
- 反馈文件保留用户原话和已解析操作，只有 select/continue 更新 selected；refine/redo 不把不满意的方案标记为认可。用户偏好可另外追加真实 history 事件；测试只在临时目录运行。

### 调整候选与会话控件

feedback/followup 同样支持 `mode=adjust`，此时不要传 variants。示例：

```json
{"mode":"adjust","add_count":2,"remove":"lowest-two","instruction":"更关注建筑结构设计","user_message":"增加两款新 skill，并移除最低分的两款"}
```

add_count 支持 2（默认）或 0；remove 为明确的 variant ID 数组（默认空），或 lowest-two。后者读取父轮 ranking.json，排除基线、失败和待核验项，遇到评分不足或跨淘汰边界并列时拒绝，协调者需按 continuation.md 向用户澄清。保留 ID 自动计算，移除原件不会被删除。不能提交空操作或删光候选而不补充。

新增数量大于零时，lineage.status 为 discovery-required。脚本只记录计划，不把计划当成已发现的 skill。协调者调查完成后记录 `added_candidates`（ID/来源/版本）和 `final_variants`，快照齐全后将状态改为 handoff-ready；若实际不足两款，记录原因与实际名单。同一 skill 不重复计数。报告仅比较本轮实际重新执行的结果。

report 会输出 interaction.json。action、selection、adjustment 可作为可用原生提问工具的 questions 参数；协调者按阶段发送，不能一次把所有问题堆给用户。根据当前动作删除无关选项或补上“全部方案”。用户回复需映射到真实 variant ID，执行前重新核对轮次、名单和低分移除范围。不得把 JSON 生成成功当成控件已展示，也不得把控件默认选项当成用户回复。该脚本不会改变客户端界面。

## 候选元数据（向后兼容）

新增可选字段 candidate_type（skill/toolkit）、repository、entrypoint、modules_allowed、modules_used、stars_status、stars、stars_checked_at、scores、score_evidence、reason、limitations。字段含义和五维权重见 discovery.md。register 在有 scores 时校验并保存 selection_priority；缺少新字段的旧记录仍可读取。GitHub stars 未获取是 unknown，非GitHub为 not_applicable，两者都不冒充零星。

将本轮已选记录复制到 variants manifest，或在 run/discovery.json 的 candidates 中以 skill_id/id 对应。packet 只将 artifacts 中的交付物复制给裁判；不把 discovery、来源、stars或选型分放进匿名包。report 从本轮元数据生成首页，并从各 execution.json 读取实际 modules_used；没有记录明确显示缺失。snapshot 使用候选入口为根，工具包需将必需模块和共享资源物化到同一根后再固定，不能漏掉根外引用。实际入口不是根SKILL.md时，保留原结构并写来源清单，选择官方适配入口；不凭空重写其方法。

报告的来源URL仅接受http/https，快照和执行文件链接从本轮真实文件生成。历史报告不自动重建，不改变旧排名或把补充候选混进旧轮。
