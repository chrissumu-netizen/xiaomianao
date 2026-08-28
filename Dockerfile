# 小棉袄的成长树洞 —— Hugging Face Space 运行环境
# 说明：Hugging Face 已弃用内置 Streamlit SDK，改用 Docker 模板运行 Streamlit 应用
FROM python:3.11-slim

WORKDIR /app

# 安装依赖（单独 COPY 可利用 Docker 构建缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# HF Docker Space 默认端口为 7860
EXPOSE 7860

CMD ["streamlit", "run", "app.py", \
     "--server.port=7860", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
