# 候选调查与入选

## 覆盖与停止

先查历史，再用任务词、同义词、工具包、热门项目及用户指定来源寻找约8–12个候选，尽量覆盖至少四个独立维护来源。不同子目录、fork或适配版不自动算独立来源。目录站只作线索，深入审查最相关者的真实入口和资源。用户指定项目必须明确审查结论；不足目标时写明已查范围与原因，不编造候选。

将匹配的单skill与完整toolkit都纳入；固定入口、允许模块、依赖和版本。包内模块协作属于该候选，跨候选读答案或临时借方法不允许。平台适配版优先核验；不能仅因原版面向其他客户端就排除。继承同一模型到包内子代理，关闭跨模型/自动分层选项；不能满足时记录限制。

覆盖目标完成，且适配候选已核对工作流、依赖和许可后停止；若搜索趋于重复、访问阻塞或确实稀缺，也可停止并说明。不要承诺穷尽生态。历史优胜者不自动占位，尽量保留一个高度匹配的新项目。先展示候选表再自动执行，不新增常规审批。

## 入选优先级（不等于结果质量）

| 维度 | 权重 | 核验内容 |
|---|---:|---|
| task_fit | 35 | 是否直接覆盖目标产物与领域 |
| workflow | 25 | 工作流完整、证据核验和失败处理 |
| compatibility | 15 | 当前工具、模型、依赖和权限能否执行 |
| stars | 15 | 仓库关注度，记录查询日期和来源 |
| maintenance | 10 | 维护、文档、可追溯版本；不以提交频率单独判断 |

前四个非stars维度由协调者按0–5评分并逐项给证据。stars分为 `min(5, log10(1 + stars))`，例如约10/100/1000/10000/100000 stars对应1/2/3/4/5分。这是透明的启发式，不是有效性概率。

GitHub仓库总stars不能写成某个子skill独立获得的认可；共用仓库应展示同一repo标识。非GitHub来源stars_status=not_applicable，其他85%权重重新归一。GitHub读取失败为unknown，必须保留缺失标记：可给其余维度暂定分，但不能假装零星或完成热度比较。取得实际star值才用known。star值不能靠记忆填。

资格先于分数：模型无法统一、关键资源缺失或任务不匹配，不能靠高star补偿。综合分只辅助选型，允许基于适配性、多样性和新项目价值调整，但记录原因。产物裁判不得看到这些分数或stars，也不把它们加入质量rubric。

## 文件与状态

`discovery.md`记录检索词、日期、来源、覆盖范围、停止理由和漏检补充。`discovery.json`结构：

```json
{"queries": ["任务词"], "searched_at": "YYYY-MM-DD", "stop_reason": "实际理由", "candidates": [
  {"id": "example", "name": "Example", "source": "https://github.com/owner/repo", "repository": "owner/repo", "version": "commit", "candidate_type": "toolkit", "entrypoint": "SKILL.md", "modules_allowed": ["planning"], "modules_used": [], "stars_status": "known", "stars": 1234, "stars_checked_at": "YYYY-MM-DD", "scores": {"task_fit": 4, "workflow": 4, "compatibility": 5, "maintenance": 4}, "score_evidence": {"task_fit": "证据", "workflow": "证据", "compatibility": "证据", "maintenance": "证据"}, "status": "selected", "reason": "实际入选理由", "limitations": "实际局限"}
]}
```

status为selected / excluded / pending_review / not_discovered；not_discovered用于事后明确发现的漏检，不代表知道所有未发现项目。failed属于执行记录，不是事后筛选理由。不得覆盖原调查，补充带日期的说明。已选项元数据复制到注册记录和运行manifest；执行完成从execution.json补modules_used，而非把允许模块当实际使用。

registry的旧字段继续有效，新字段可选；缺失展示“未记录”，不回填臆测。来源和快照以运行时数据为准，报告不读取今天的registry替代过去版本。首次生成前冻结选型记录，不向评估者传递discovery或映射。
