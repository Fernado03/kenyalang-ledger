FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq for psycopg2; libgl1/libglib2.0-0 satisfy OpenCV + torch runtime linking.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt constraints.txt ./
# The default PyPI torch wheel bundles ~3GB of NVIDIA CUDA driver libraries we
# never call: compose ships no GPU and the OCR engine runs on CPU. The CPU wheel
# index drops the image from ~10GB to ~2.5GB.
RUN pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        -c constraints.txt -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
