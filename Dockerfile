FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 wget \
    && rm -rf /var/lib/apt/lists/*

# Download bold fonts for Pillow text overlay
RUN mkdir -p /app/fonts && \
    wget -q "https://github.com/google/fonts/raw/main/ofl/Anton/Anton-Regular.ttf" -O /app/fonts/Anton-Regular.ttf && \
    wget -q "https://github.com/google/fonts/raw/main/apache/oswald/static/Oswald-Bold.ttf" -O /app/fonts/Oswald-Bold.ttf

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
