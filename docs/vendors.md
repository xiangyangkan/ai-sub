# AI 大模型领域 Vendor 评级

数据来源：[releasebot.io/updates/alphabetical](https://releasebot.io/updates/alphabetical)

评级标准基于 vendor 在 AI 大模型领域的核心程度和影响力。

---

## T0 - 核心大模型厂商

直接研发和发布前沿大语言模型的公司，是行业动态的第一信息源。

| Vendor | Slug | 说明 |
|--------|------|------|
| OpenAI | `openai` | GPT 系列模型，ChatGPT，行业标杆 |
| Anthropic | `anthropic` | Claude 系列模型，Claude Code |
| Google | `google` | Gemini 系列模型，Gemini API/CLI |
| Meta | `meta` | Llama 开源模型系列，推动开源生态 |
| Deepseek | `deepseek` | DeepSeek 系列模型，开源影响力大 |
| xAI | `xai` | Grok 系列模型 |
| Mistral | `mistral` | 欧洲头部大模型公司，开源+闭源双线 |
| Qwen | `qwen` | 通义千问系列，阿里巴巴出品 |
| MiniMax | `minimax` | MiniMax 系列模型，海螺 AI |
| Z.AI | `zai` | 智谱 GLM 系列模型 |

## T1 - 重要 AI 产品与平台

基于大模型构建核心产品，或提供关键 AI 基础设施的公司。

| Vendor | Slug | 说明 |
|--------|------|------|
| Microsoft | `microsoft` | Copilot 全家桶，Azure OpenAI 服务 |
| Cursor | `cursor` | AI-first IDE，AI 编程标杆产品 |
| Windsurf | `windsurf` | Codeium 出品的 AI 编程 IDE |
| Cline | `cline` | 开源 AI 编程助手（VS Code 插件） |
| TRAE | `trae` | 字节跳动 AI IDE |
| Kiro | `kiro` | AWS 出品的 AI IDE |
| Perplexity | `perplexity-ai` | AI 搜索引擎 |
| Midjourney | `midjourney` | AI 图像生成，设计领域标杆 |
| Runway AI | `runwayai` | AI 视频生成 |
| Pika | `pika` | AI 视频生成 |
| Eleven Labs | `eleven-labs` | AI 语音合成，TTS 领域领先 |
| Replicate | `replicate` | AI 模型托管与推理平台 |
| Replit | `replit` | AI 编程平台 |
| Databricks | `databricks` | Data + AI 统一平台 |

| Volcengine | `volcengine` | 字节火山引擎，豆包大模型 |

## T2 - AI 生态相关

在 AI 生态中扮演重要角色：提供 AI 集成能力、垂直领域 AI 应用或 AI 开发工具。

| Vendor | Slug | 说明 |
|--------|------|------|
| GitHub | `github` | GitHub Copilot，开发者 AI 工具 |
| Amazon | `amazon` | AWS Bedrock，云端 AI 服务 |
| Vercel | `vercel` | AI SDK，前端 AI 集成 |
| Cloudflare | `cloudflare` | Workers AI，边缘 AI 推理 |
| AssemblyAI | `assemblyai` | 语音识别与理解 API |
| Deepgram | `deepgram` | 语音识别 AI |
| Cartesia | `cartesia` | AI 语音合成 |
| Fish Audio | `fish-audio` | AI 语音合成，开源 TTS |
| Hume | `hume` | 情感 AI，多模态表达理解 |
| Harvey | `harvey` | 法律领域 AI 应用 |
| Moondream | `moondream` | 小型视觉语言模型 |
| n8n | `n8n` | 工作流自动化，AI Agent 编排 |
| BoltAI | `boltai` | macOS AI 客户端 |
| Ampcode | `ampcode` | AI 编程工具 |
| Dia | `dia` | AI 对话产品 |
| Exa | `exa-ai` | AI 搜索 API |
| Inworld | `inworld` | 游戏 NPC AI |


---

## 推荐监控配置

根据实际需求选择监控范围：

### 精简版（仅 T0 核心厂商）

```
RELEASEBOT_VENDORS=["openai","anthropic","google","meta","deepseek","xai","mistral","qwen","minimax","zai"]
```

### 标准版（T0 + AI 编程工具）

```
RELEASEBOT_VENDORS=["openai","anthropic","google","meta","deepseek","xai","mistral","qwen","minimax","zai","cursor","windsurf","cline","trae","kiro"]
```

### 完整版（T0 + T1）

```
RELEASEBOT_VENDORS=["openai","anthropic","google","meta","deepseek","xai","mistral","qwen","minimax","zai","microsoft","cursor","windsurf","cline","trae","kiro","perplexity-ai","midjourney","runwayai","pika","eleven-labs","replicate","replit","databricks","volcengine"]
```
