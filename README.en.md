<p align="center"><a href="README.md">← 中文</a> · <strong>English</strong></p>

<p align="center">
  <img src="assets/skill-arena-banner.png" alt="Skill Arena: describe a task, compare independent skill outputs, review the evaluation, and choose what to do next" width="100%">
</p>

<h1 align="center">Skill Arena</h1>
<p align="center"><strong>One task. Independent skill trials. Results you can compare.</strong></p>

---

## What does it do?

When several skills look useful, Skill Arena helps you find out which one works best for your task. It discovers candidates, lets each complete the task independently, and compares their actual outputs.

**Just describe your task. Attach materials if you have them; they are optional.**

For example, to plan a journal paper, it selects 3–5 relevant academic skills, produces a full plan with each, and asks a separate Codex evaluator to explain their strengths, weaknesses, and suitable uses.

## How do I use it?

On first use, choose a local file directory and whether to remember it globally. A fixed directory is reused without asking again; you can also use it for this task only.

Add this project to Codex as a skill, then say:

> Use $skill-arena to plan an English journal paper on reinforcement learning for structural design.

It also works for other tasks:

> Use $skill-arena to create a presentation about my research findings.

Not installed yet? Download this project and ask Codex to **“Read this project's SKILL.md and use it for my task: …”**

## What happens next?

| Step | What you receive |
| --- | --- |
| **Find candidates** | A broad search followed by 3–5 relevant skills or toolkits |
| **Run independently** | A complete output from each candidate; toolkits can use their own modules |
| **Compare results** | Rankings and evidence against the same task requirements |
| **Keep records** | Full outputs, a comparison report, and skill sources for future reuse |

All candidates use the **same Codex model**. Equal runtime or token budgets are not required. Full comparisons include two fixed references: a **plain-prompt baseline** and a **multi-skill collaboration baseline**. The latter prioritizes complementary skills for subtasks such as literature review, hypothesis generation, and experiment critique, then integrates its own work without reading or combining other candidates’ answers.

## How are candidates selected?

The initial search considers about **8–12 candidates** from different sources. Task fit, workflow, compatibility, **GitHub stars**, and maintenance guide the choice of 3–5 candidates. Projects you name are reviewed explicitly. If too few suitable candidates exist, the report says so.

**GitHub skills or toolkits with fewer than 500 stars are excluded unless you explicitly name them.** Projects with unverified star counts are not automatically selected; a shortage of candidates does not lower the threshold.

Both individual skills and complete toolkits can participate. A toolkit may use its internal modules, while candidates remain independent. Internal agents also use the same model. **Stars inform selection; actual outputs determine quality scores.**

> Use $skill-arena to plan my paper. Please also consider academic-research-skills and its Codex version.

Before execution, you see the candidates and selection reasons. Each skill introduction in the report lists only its source, stars, short description, and latest project update.

## Can I continue after reviewing the results?

Yes. Each round offers **selectable conversation prompts and a text input**:

| Action | What to provide |
| --- | --- |
| **Refine existing results** | Select candidates and describe improvements |
| **Redo results** | Select one, several, or all candidates; optionally add requirements |
| **Satisfied, continue** | Select candidates and describe the next task |
| **None are satisfactory, adjust candidates** | Add 2 new skills and optionally remove named candidates or the 2 lowest-scoring skills |
| **Keep for later** | Remember your choice without starting another task |

Options show **skill names and brief distinguishing features**, so you do not need to remember A, B, or C. Choose a single option or type multiple names. If conversation controls are unavailable, reply in plain text.

**Example:** Select a literature-review result → choose “Satisfied, continue” → enter “Use this review to write a paper outline.”

**If none are satisfactory:** Choose “Add 2 new skills” and “Remove the 2 lowest-scoring skills,” then add “Focus more on structural design.” Adding and removing can also be done separately. If tied scores make removal ambiguous, you choose by name.

Continuation keeps each selected skill with its own work. Removing a candidate affects the next round only; previous results remain available.

## How do I read the results?

Open **report.html** to read all outputs in one place:

- **Choose a name at the top** to jump to that skill's full output.
- **Expand or collapse** individual outputs, chapters, and references, or all sections at once.
- **Read outputs first, evaluation last.** Lists, tables, and useful diagrams support reading; rankings and scoring evidence appear at the end.

**Example:** Click `hypothesis-generation` → read its complete plan → collapse finished chapters → click the evaluation link. Original files are also downloadable from the report.

Close scores may tie. Uncertainty is disclosed. A better result in one task does not establish that a skill is universally better.

## What if I run it on a remote server?

Skill Arena first asks whether to send the final report to your computer, using the directory confirmed above.

- **You choose delivery and a direct channel works:** it selects the channel expected to finish fastest, transfers the report, and verifies it locally.
- **Direct delivery is unavailable:** choose “Transfer through a reverse connection” or “Download it myself without Codex assistance.”
- **You decline delivery or choose manual download:** it provides the remote location and download instructions, then stops automatic transfer.

Reverse transfer uses a temporary connection that closes afterward. Other files remain available on demand. “Delivered locally” requires successful verification on your computer.

> Use $skill-arena to plan my paper. Use D:\CodexFiles for temporary files and remember it as my fixed directory.

Directory preferences are stored per computer; a server path is never treated as your local path.

<details>
<summary><strong>Want the detailed rules?</strong></summary>

The operational references below are currently in Chinese.

- [Full workflow](SKILL.md)
- [Prompt templates](references/prompts.md)
- [Candidate selection](references/discovery.md)
- [Report presentation](references/reporting.md)
- [Evaluation](references/evaluation.md)
- [First-use directory and global memory](references/onboarding.md)
- [Remote execution and local delivery](references/delivery.md)
- [File and record management](references/storage.md)
- [Refinement and continuation](references/continuation.md)
- [Research and design rationale](references/research.md)

</details>
