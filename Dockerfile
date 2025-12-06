FROM python:3.11

WORKDIR /app

# Install system deps needed by Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates libnss3 libatk1.0-0 libcups2 \
    libxcomposite1 libxrandr2 libxdamage1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libcurl4 libxkbcommon0 \
    libxshmfence1 libgbm1 libgtk-3-0 libdbus-1-3 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 🔥 INSTALLA IL BROWSER CHROMIUM PER PLAYWRIGHT
RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "bot.py"]
