# 郑州旅行助手

基于 FastAPI + LangGraph 的智能旅行助手系统。

## 项目结构

- `agent/` - LangGraph 智能体（意图分类、酒店查询、天气、预订）
- `backend/` - FastAPI REST API（酒店查询接口、订单接口）

## 快速开始

1. 复制环境变量文件：`cp .env.example .env`
2. 填写 `.env` 中的 API Key
3. 安装依赖：`pip install -r agent/requirements.txt`
4. 运行 Agent：`python agent/main.py`