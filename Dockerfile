# AI Newsletter Bot Dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 赋予执行权限
RUN chmod +x run.sh

# 创建 volumes 用于持久化存储数据（如果需要）
VOLUME ["/app/data"]

# 默认命令
CMD ["bash", "run.sh"]
