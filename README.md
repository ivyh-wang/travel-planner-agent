# 旅游攻略 Agent (travel-planner-agent)

一个**独立可运行的 Python 命令行 Agent**，帮你做两件事：

1. **生成旅游攻略** —— 根据目的地 + 天数，产出完整攻略（每日行程 / 美食清单 / 预算估算 / 地图与交通 / 避坑贴士）。
2. **采集帖子 / 视频里的推荐** —— 粘贴帖子或视频链接，自动抓取内容，用大模型提取其中的美食 / 地点推荐，**预览确认后写入采集库**（按城市分类的 Markdown + JSON）。之后生成该城市攻略时，会**优先采用你采集库里的推荐并标注来源链接**，实现个性化。

## 特性

- 多模型可切换：`openai` / `deepseek` / `qwen`(通义) / `anthropic` / `mock`（无 Key 也能跑通流程）。
- 采集库：本地 `library/<城市>/` 下同时生成结构化 `.json` 与可读 `.md`，并有 `index.json` 总索引。
- 提取防幻觉：只提取原文明确提及的内容，结构化校验后入库；入库前先预览，可逐条取舍。
- 视频：自动取平台字幕 / 简介文本（YouTube 字幕、B站等），不做语音识别；取不到时提示改贴文本。

## 安装

```bash
cd travel-planner-agent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
# 可选：anthropic / qwen / 视频字幕支持
pip install -e ".[anthropic,qwen,video]"
cp .env.example .env   # 然后填入 TRAVEL_API_KEY
```

> 没有 API Key 也能体验：`TRAVEL_PROVIDER=mock` 即可（见下方演示）。

## 使用

### 0) 分阶段旅行规划专家（推荐）

`plan` 模式遵循「多轮、分阶段协作」的旅行规划专家设定：不会一次性输出全部内容，而是
先收集基础信息 → 整体框架 → 住宿与交通 → 每日行程 → 美食/体验 → 最终攻略，每阶段主动
指出缺失信息与风险、比较方案并给出推荐，等待你确认后再继续。会**优先采用你采集库里的
推荐并标注来源**。

```bash
python -m src.main plan "东京 5日游，爱吃拉面看夜景" --city 东京
```

交互提示：输入文字=补充/确认；`继续`=推进下一阶段；`完成`=输出并保存最终攻略到 `guides/`；`退出`=结束。
快速出攻略仍可用 `guide` 子命令（一次性生成）。

### 1) 采集一条帖子 / 视频推荐

```bash
# 粘贴链接自动抓取
python -m src.main collect "https://example.com/xxx-travel-post" --city 东京

# 或直接粘贴文本（无需联网抓取，适合视频字幕/简介）
python -m src.main collect --text "这家拉面店汤头超浓，地址在XX区..." --city 东京

# 指定 provider
python -m src.main collect "https://..." --city 东京 --provider deepseek
```

流程：抓取 → LLM 提取推荐 → 终端预览 → 你确认要保存的条目 → 写入 `library/东京/`。

### 2) 生成攻略（自动采用采集库）

```bash
python -m src.main guide "东京 5日游，爱吃拉面和看夜景" --city 东京
# 输出：guides/东京-5日游.md
```

攻略里凡来自采集库的推荐都会带 `[来源](url)`；库未覆盖处用通用知识并标注「（通用建议）」。

### 3) 管理采集库

```bash
python -m src.main library list                 # 列出所有城市及条数
python -m src.main library show --city 东京      # 查看某城市条目
python -m src.main library search "拉面"         # 全文搜索
python -m src.main library remove --city 东京 --index 0   # 删除第 0 条
```

## 无 Key 演示（mock）

```bash
export TRAVEL_PROVIDER=mock        # Windows: set TRAVEL_PROVIDER=mock
python -m src.main collect --text "推荐去XX观景台看夜景，还有一家本地拉面店" --city 演示市
python -m src.main guide "演示市 3日游" --city 演示市
```

## 项目结构

```
travel-planner-agent/
├── src/
│   ├── main.py            # CLI 入口（collect / guide / plan / library）
│   ├── config.py          # 读取 .env
│   ├── llm.py             # 多 provider LLM 客户端（含 mock、多轮 chat）
│   ├── collect/
│   │   ├── fetcher.py     # URL 抓取（网页 + 视频字幕）
│   │   ├── extractor.py   # LLM 提取 + JSON 解析校验
│   │   └── library.py     # 采集库读写
│   ├── guide/
│   │   └── generator.py   # 攻略生成
│   └── prompts/
│       ├── extract_prompt.py   # 采集提取提示
│       ├── guide_prompt.py     # 一次性攻略提示
│       └── planner_prompt.py   # 分阶段规划专家提示
├── library/               # 采集库（运行时生成）
├── guides/                # 生成的攻略
└── tests/
```

## 推送到 GitHub

本机未预装 `gh`，按以下步骤自行推送：

```bash
git remote add origin git@github.com:<你的用户名>/travel-planner-agent.git
git branch -M main
git push -u origin main
```

或用 GitHub CLI（先 `winget install gh` 或下载安装，再 `gh auth login`）：

```bash
gh repo create travel-planner-agent --private --source=. --remote=origin
git push -u origin main
```

> 注意：`.env` 含密钥，已在 `.gitignore` 忽略；请勿把真实 Key 提交到仓库。
