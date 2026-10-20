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

protocol.json 初始为 draft；派发前填写统一 Codex 模型、网络策略及任务约束，设为 frozen。equal_budget 固定为 false；user_limits 仅记录用户主动提出的总限制，没有则为 null，不要求用户填写。没有附件时 inputs 可为空。rubric.json 除 weights、tie_threshold 外应加入 anchors、hard_conditions；评估者依据这些字段判断，脚本仅校验算术与数据完整性。

history-record.json 必备 run_id、task_tags、skill_versions、environment、status、report_path、synthetic=false。应附 ranking、failure_reasons、user_feedback、limitations；禁止把演示测试当作实测。find 是简单大小写不敏感检索，语义相似性由协调代理复核。

不得自动清理 runs、registry 或 history；临时文件清理只限确认位于 DATA_ROOT/tmp 的路径。第三方快照、用户输入、运行报告默认不提交 Git。发布源码前检查凭据和私人路径，保留 .gitignore。脚本的路径检查不提供安全沙箱；子代理共享文件系统。
