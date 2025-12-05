FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

CMD ["python", "bot.py"]
