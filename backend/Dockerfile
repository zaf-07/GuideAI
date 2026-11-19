FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-vision.txt ./requirements-vision.txt
RUN pip install --no-cache-dir -r requirements.txt -r requirements-vision.txt

COPY backend ./backend
# Keep the detector weight next to the backend so it is available in the
# container without an internet download on first use.
COPY apps/mobile/assets/models/yolo11n.onnx ./backend/models/yolo11n.onnx

ENV PORT=8000
ENV CORS_ORIGINS="*"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
