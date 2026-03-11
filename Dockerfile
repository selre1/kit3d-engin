FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip nodejs npm libgomp1 \
  && rm -rf /var/lib/apt/lists/*

RUN npm config set prefix /usr/local \
  && npm install -g gltf-pipeline

COPY bin/pg2b3dm-linux-x64.zip /tmp/pg2b3dm.zip
RUN unzip /tmp/pg2b3dm.zip -d /tmp/pg2b3dm \
  && chmod +x /tmp/pg2b3dm/pg2b3dm \
  && mv /tmp/pg2b3dm/pg2b3dm /usr/local/bin/pg2b3dm \
  && rm -rf /tmp/pg2b3dm /tmp/pg2b3dm.zip

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "celery -A worker.celery_app worker -l info -E -Q ${CELERY_QUEUE} -P prefork --concurrency ${CELERY_CONCURRENCY:-4}"]
