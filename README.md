# 郑州旅行助手

基于 **FastAPI + LangGraph + DeepSeek** 的多轮对话旅行助手，支持酒店查询、预订、天气查询和郑州本地知识问答。

## 项目结构

```
zhengzhou-travel/
├── main.py           # FastAPI 入口（/api/chat、/health）
├── run_terminal.py   # 本地终端交互调试
├── view_memory.py    # 查看指定 session 的对话记忆
├── graph.py          # LangGraph 状态图与意图路由
├── nodes.py          # 各业务节点（分类、查询、预订、天气、闲聊）
├── state.py          # AgentState 类型定义
├── paths.py          # 项目路径与 SQLite 数据库位置
├── db.py             # PostgreSQL 连接校验（会话记忆）
├── data/             # SQLite 数据目录（运行时生成 hotel.db）
├── init.sql          # Docker 首次启动 Postgres 时的说明脚本
├── requirements.txt
├── tests/            # 基础单元测试
├── Dockerfile
└── docker-compose.yml
```

## 架构概览

```
用户输入
   ↓
classifier（意图分类）
   ↓
┌──────────┬──────────┬──────────┬────────────┐
│  search  │   book   │  weather │ knowledge  │
│ 酒店查询  │ 酒店预订  │ 天气查询  │ 本地问答    │
└──────────┴──────────┴──────────┴────────────┘
```

## 数据存储

业务数据与会话记忆分开存储：

| 用途 | 存储 | 位置 / 机制 |
|------|------|-------------|
| 多轮对话记忆 | PostgreSQL | LangGraph `PostgresSaver` checkpoint |
| 酒店库存 | SQLite | `data/hotel.db` → `hotel` 表 |
| 订单 | SQLite | `data/hotel.db` → `order` 表 |

- **SQLite** 路径由 `paths.py` 管理，使用相对路径 `data/hotel.db`，无需硬编码绝对路径。
- **PostgreSQL** 仅用于 LangGraph 会话持久化；`checkpointer.setup()` 会自动创建 checkpoint 表。

## 环境要求

- Python 3.10+
- PostgreSQL 15（可用 Docker 提供）
- API Key：DeepSeek、高德地图 Web 服务

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `AMAP_API_KEY` | 高德地图 Web 服务密钥 |
| `DB_URI` | PostgreSQL 连接串（密码需与 `docker-compose.yml` 一致） |

### 2. 启动 PostgreSQL

```bash
docker compose up db -d
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行

**终端调试（推荐本地开发）：**

```bash
python run_terminal.py
```

默认 `thread_id` 为 `local_debug_user`，输入 `quit` / `exit` / `退出` 结束。

**HTTP API：**

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

请求示例：

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"user-001\", \"message\": \"郑州东站附近有什么酒店？\"}"
```

**查看会话记忆：**

```bash
python view_memory.py local_debug_user
# 或指定其他 session_id
python view_memory.py user-001
```

### 5. Docker 一键部署

```bash
docker compose up -d --build
```

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | API |
| http://localhost:8000/health | 健康检查 |
| http://localhost:8000/docs | Swagger 文档 |

## 对话能力

| 意图 | 触发示例 | 实现 |
|------|----------|------|
| `query` | 「洛阳龙门附近 500 元以内的酒店」 | 高德 POI + SQLite 动态补库存 |
| `book` | 「订第一家，明天住两晚，我叫张三」 | 解析参数 + SQLite 扣库存写订单 |
| `weather` | 「郑州明天天气怎么样」 | Open-Meteo 7 天预报 + LLM 解读 |
| `knowledge` | 「少林寺怎么去」 | 郑州本地旅行问答 |

多轮预订依赖上一轮 `hotels_list`（保存在 PostgreSQL checkpoint 中）。

## 异常处理

外部依赖均带有 `try/except`，失败时返回友好提示而非直接崩溃：

- 高德 API → 返回空列表，提示未找到酒店
- Open-Meteo → 回退默认坐标或提示服务不可用
- SQLite → 捕获 `sqlite3.Error`，返回数据库错误信息
- PostgreSQL → 捕获 `psycopg.Error`，启动或调用时报错

## 测试

```bash
pip install pytest
pytest tests/ -v
```

当前包含 3 个基础测试：

1. `test_route_intent` — 意图路由是否正确
2. `test_hotel_db_path` — SQLite 路径是否为项目相对路径
3. `test_fetch_amap_hotels_without_key` — 未配置 API Key 时是否安全降级

## 常见问题

**Q: 终端连不上数据库？**

本地运行时 `run_terminal.py` 会把 `DB_URI` 中的 `@db:` 自动替换为 `@localhost:`。确保已执行 `docker compose up db -d`。

**Q: 查询到的酒店在哪里？**

高德返回的 POI 会写入 `data/hotel.db`；首次查询后该文件自动创建。

**Q: `data/hotel.db` 要提交到 Git 吗？**

不需要，`.gitignore` 已忽略 `*.db` 文件。
