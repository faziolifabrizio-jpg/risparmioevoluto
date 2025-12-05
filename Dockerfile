FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

# Copia tutto il codice
COPY . .

# Installa tutte le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser deps
RUN playwright install --with-deps chromium

# Avvio bot
CMD ["python", "bot.py"]
