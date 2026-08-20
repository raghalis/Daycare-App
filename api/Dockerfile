FROM python:3.12-slim

WORKDIR /app

# ffmpeg grabs the still images for Live View - pulled directly from each
# camera's RTSP source, independent of whether MediaMTX currently has that
# path open (it doesn't, on-demand, until a viewer connects).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
