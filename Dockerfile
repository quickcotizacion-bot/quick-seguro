FROM python:3.11-slim

# Dependencias del sistema
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi-dev \
    libjpeg-dev \
    libpng-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-spa \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads outputs

EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "app:app"]
