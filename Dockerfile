# 使用官方 Python 基礎映像
FROM python:3.10-slim

# 安裝 FFmpeg (語音房必備組件)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# 設定容器內的工作路徑
WORKDIR /app

# 先複製零件清單並安裝，利用快取加速
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有代碼到容器
COPY . .

# [核心修正] 直接指定 Python 執行路徑
ENTRYPOINT ["python"]
CMD ["main.py"]
