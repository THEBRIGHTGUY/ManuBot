FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# On a fresh host the Chroma embedding model (~80MB) is downloaded on first use.
# Pre-warm sqlite is handled by the bot itself at startup (db.warm_up()).

CMD ["python", "-u", "bot.py"]