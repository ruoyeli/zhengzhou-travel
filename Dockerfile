# 1. 使用官方 Python 3.10 基础镜像
FROM python:3.10-slim

# 2. 设置容器内的工作目录
WORKDIR /app

# 3. 把本地的 requirements.txt 复制到容器里并安装依赖
COPY requirements.txt .
# 清空代理变量，避免构建环境里的代理影响 pip 安装。
RUN HTTP_PROXY="" HTTPS_PROXY="" http_proxy="" https_proxy="" pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 4. 把当前目录下的所有代码复制到容器的 /app 目录下
COPY . .

# 5. 暴露 8000 端口
EXPOSE 8000

# 6. 容器启动时运行 FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
