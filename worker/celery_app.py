import os
from dotenv import load_dotenv
from celery import Celery

load_dotenv()

celery_app = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//"),
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_default_queue=os.getenv("CELERY_QUEUE", "import_jobs"),
   # task_acks_late=os.getenv("CELERY_ACKS_LATE", "false").lower() == "true",
    worker_prefetch_multiplier=int(os.getenv("CELERY_PREFETCH", "1")),
    broker_heartbeat=int(os.getenv("CELERY_BROKER_HEARTBEAT", "120")),
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_transport_options={
        "heartbeat": int(os.getenv("CELERY_BROKER_HEARTBEAT", "120")),
    },
)
