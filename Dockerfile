FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*
COPY requirements-ml.txt ./
ARG INSTALL_SEMANTIC_MODEL=true
RUN if [ "$INSTALL_SEMANTIC_MODEL" = "true" ]; then pip install --no-cache-dir torch==2.9.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements-ml.txt; fi

COPY . .
RUN if [ "$INSTALL_SEMANTIC_MODEL" = "true" ]; then python scripts/download_model.py; fi
RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "120", "app:app"]
