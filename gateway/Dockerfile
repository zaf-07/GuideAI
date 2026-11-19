FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
ENV PORT=8000
# One worker: the rate limits and the token budget are in-process. A
# multi-worker or internet-facing deployment needs them enforced at a shared
# gateway instead, or each worker will allow the full budget on its own.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
