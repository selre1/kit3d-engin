import os
from dotenv import load_dotenv
from celery import Celery

load_dotenv()

celery_app = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_default_queue=os.getenv("DEFAULT_QUEUE", "import_jobs"),
    worker_prefetch_multiplier=int(os.getenv("CELERY_PREFETCH", "1")),
    broker_heartbeat=int(os.getenv("CELERY_BROKER_HEARTBEAT", "120")),
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    task_track_started=True,
    result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "86400")),
    broker_transport_options={
        "heartbeat": int(os.getenv("CELERY_BROKER_HEARTBEAT", "120")),
    },
)
