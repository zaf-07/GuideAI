FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
ARG TORCH_INDEX_URL=
RUN if [ -n "$TORCH_INDEX_URL" ]; then pip install --no-cache-dir torch torchvision --index-url "$TORCH_INDEX_URL"; fi \
    && pip install --no-cache-dir -r requirements.txt
COPY *.py ./
ENV PORT=8000
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
