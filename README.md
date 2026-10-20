# Skill Arena

多 skill 独立试做、独立评估、历史复用的 Codex skill。默认自动选择 3–5 个候选，另设无候选 skill 基线，交付本地 HTML/Markdown 对比报告及完整原件。

入口为 [SKILL.md](SKILL.md)，可直接让 Codex 读取该绝对路径并执行。若要加入技能目录，将整个文件夹复制到当前 Codex 支持的 skills 位置，再重新载入技能；本次交付未修改全局配置。数据根目录使用本项目 data/，未来安装技能后仍沿用此绝对路径。

示例：

> 请读取本项目的 SKILL.md 并执行。任务是……，输入材料是……，输出要求是……。数据保存在本项目 data 目录（请解析为绝对路径）。自动选候选，独立试做并排名。

执行依赖当前 Codex 的子代理和文件工具；候选调查还需要网络检索。Python 3.10+ 仅用于本地索引、快照和报告汇总，无第三方包。此版本以独立代理上下文运行；不声称提供 OS 进程或文件访问隔离。没有代理工具时只输出待执行包并明确未完成。

提示词模板见 [prompts.md](references/prompts.md)，评分约定见 [evaluation.md](references/evaluation.md)，命令和存储见 [storage.md](references/storage.md)，研究依据见 [research.md](references/research.md)。

源码可单独推送到 GitHub；data/、tmp/ 和第三方快照默认排除。尚未对真实学术候选进行效果排名，测试不写入真实历史。
