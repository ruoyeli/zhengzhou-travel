# 郑州旅行助手 Agent

一个面向本地旅行场景的多轮 AI 助手 Demo，基于 **FastAPI + LangGraph + DeepSeek + RAG** 实现酒店查询、模拟预订、天气查询和郑州本地知识问答。项目重点展示 AI 应用开发中的意图路由、工具调用、状态记忆、RAG 检索、外部 API 集成和容器化部署能力。

> 说明：酒店价格、评分、库存和订单是用于演示 Agent 工作流的模拟业务数据，不对接真实交易系统。

## 项目亮点

- 使用 `LangGraph StateGraph` 编排多轮 Agent 流程：先识别用户意图，再分发到酒店查询、预订、天气或知识问答节点，最后统一聚合回复。
- 支持多意图输入，例如用户可以在一轮对话中同时询问酒店和天气，系统会 fan-out 到多个业务节点处理。
- 使用 `PostgreSQL + PostgresSaver` 持久化 LangGraph checkpoint，实现 session 级会话记忆；用户说“订第一家”时可以引用上一轮查询结果。
- 接入高德地图 POI 查询酒店，接入 Open-Meteo 获取天气数据，并通过 LLM 将结构化结果转成自然语言回复。
- 基于 `PyPDFLoader + RecursiveCharacterTextSplitter + HuggingFace Embeddings + Chroma` 构建本地 RAG 知识问答。
- 使用 `SQLite` 管理模拟酒店库存和订单，预订时通过事务和条件更新避免库存不足仍生成订单。
- 提供 FastAPI HTTP 接口、终端调试脚本、会话记忆查看脚本、Docker Compose 部署和 pytest 基础测试。

## 技术栈

| 分类 | 技术 |
|------|------|
| Web API | FastAPI, Uvicorn, Pydantic |
| Agent 编排 | LangGraph, LangChain |
| LLM | DeepSeek Chat, OpenAI-compatible API |
| RAG | Chroma, HuggingFace Embeddings, PyPDFLoader |
| 数据存储 | PostgreSQL checkpoint, SQLite business data |
| 外部 API | 高德地图 Web 服务, Open-Meteo |
| 工程化 | Docker, Docker Compose, pytest, python-dotenv |

## 架构概览

```text
用户输入
  |
  v
FastAPI / Terminal
  |
  v
LangGraph classifier
  |
  +--> search     高德 POI + SQLite 酒店库存
  +--> book       LLM 参数抽取 + SQLite 事务扣库存
  +--> weather    Open-Meteo + LLM 解读
  +--> knowledge  Chroma 向量检索 + RAG 回答
  |
  v
aggregator 聚合自然语言回复
  |
  v
PostgreSQL checkpoint 保存多轮会话状态
```

## 核心能力

| 能力 | 示例 | 实现方式 |
|------|------|----------|
| 酒店查询 | “郑州东站附近 500 元以内的酒店” | LLM 抽取地点/预算，高德 POI 查询，SQLite 写入模拟库存 |
| 酒店预订 | “订第一家，明天住两晚，我叫张三” | 读取 checkpoint 中的 `hotels_list`，LLM 抽取入住信息，SQLite 事务扣库存并生成订单 |
| 天气查询 | “郑州明天天气怎么样” | Open-Meteo 获取 7 天天气，LLM 生成出行建议 |
| 本地问答 | “少林寺怎么去” | Chroma 检索本地 PDF 知识库，结合 LLM 输出回答 |
| 多轮记忆 | “就订第一家” | PostgreSQL checkpoint 保存上一轮状态 |

## 项目结构

```text
zhengzhou-travel/
├── main.py              # FastAPI 入口，提供 /api/chat 和 /health
├── graph.py             # LangGraph 状态图、意图路由和 fan-out
├── nodes.py             # 分类、查询、预订、天气、知识问答、聚合节点
├── state.py             # AgentState 类型定义
├── rag.py               # PDF 加载、文本切分、Chroma 向量库检索
├── db.py                # PostgreSQL 连接校验
├── paths.py             # 项目路径、SQLite 和 Chroma 路径
├── run_terminal.py      # 本地终端调试入口
├── view_memory.py       # 查看指定 session 的 checkpoint 记忆
├── docs/                # 可公开的 RAG 示例资料
├── tests/               # 基础单元测试
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 数据设计

| 数据 | 存储 | 说明 |
|------|------|------|
| 会话状态 | PostgreSQL | LangGraph `PostgresSaver` checkpoint，保存 messages、intents、hotels_list、booking_info |
| 酒店库存 | SQLite | `data/hotel.db` 的 `hotel` 表，运行时自动创建 |
| 订单信息 | SQLite | `data/hotel.db` 的 `order` 表，运行时自动创建 |
| 知识库向量 | Chroma | `chroma_db/`，由 RAG 构建流程生成，默认不提交运行产物 |

## 快速开始

### 1. 准备环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `AMAP_API_KEY` | 高德地图 Web 服务 Key |
| `DB_URI` | PostgreSQL 连接串 |
| `API_SECRET_KEY` | 可选；配置后 `/api/chat` 需要 `x-api-key` |
| `LANGCHAIN_*` | 可选；用于 LangSmith tracing |

### 2. 启动 PostgreSQL

```bash
docker compose up db -d
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行终端调试

```bash
python run_terminal.py
```

默认 `thread_id` 为 `local_debug_user`，输入 `quit` / `exit` / `退出` 结束。

### 5. 运行 HTTP API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

请求示例：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "x-api-key: 123456" \
  -d "{\"session_id\": \"user-001\", \"message\": \"郑州东站附近有什么酒店？\"}"
```

如果没有配置 `API_SECRET_KEY`，本地开发时可以省略 `x-api-key`。

### 6. Docker Compose 一键启动

```bash
docker compose up -d --build
```

| 地址 | 说明 |
|------|------|
| http://localhost:8000/health | 健康检查 |
| http://localhost:8000/docs | Swagger 文档 |
| http://localhost:8000/api/chat | 对话接口 |

## 测试

```bash
pytest tests/ -v
```
