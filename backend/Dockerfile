FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# tesseract-ocr-bul / -eng са езиковите пакети зад OCR_LANGUAGES=bul+eng.
# Растеризирането на сканирани PDF-и е на pypdfium2 (колело от PyPI) — системен
# poppler не трябва, затова средата е еднаква тук, на Windows и в CI.
RUN apt-get update && apt-get install --no-install-recommends -y \
        tesseract-ocr \
        tesseract-ocr-bul \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
