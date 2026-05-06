FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps cho OCR (RapidOCR/onnxruntime + opencv-headless).
# libgomp1: OpenMP runtime cho onnxruntime.
# libglib2.0-0: cần bởi opencv-python-headless (dependency transient của rapidocr).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

ARG VIENG_MODE=lite
COPY requirements.txt requirements.lite.txt ./
RUN if [ "$VIENG_MODE" = "full" ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.lite.txt; \
    fi

COPY app ./app
COPY data ./data
RUN mkdir -p ./logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
