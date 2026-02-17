FROM python:3.10-slim

# 安裝系統依賴 (FFmpeg)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /app

# 複製零件清單並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有代碼
COPY . .

# 執行啟動指令
CMD ["python", "main.py"]
