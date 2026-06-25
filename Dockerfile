FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download rembg u2net model so it's baked into the image
RUN python -c "
from rembg import remove
from PIL import Image
import io
img = Image.new('RGBA', (10, 10), (255,255,255,255))
buf = io.BytesIO()
img.save(buf, format='PNG')
remove(buf.getvalue())
print('rembg model downloaded successfully')
"

COPY . .

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
