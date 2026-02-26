from loguru import logger
import sys
from pathlib import Path

def setup_logger(project_id: str, job_id: str):
    log_dir = Path("log") / project_id / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    # 콘솔 로그
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"
    )

    # 파일 로그 (Job 단위)
    logger.add(
        log_dir / f"{job_id}.log",
        level="DEBUG",
        rotation="50 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    )

    return logger

def progress(self, percent: int, message: str):
    self.logger.info(f"[PROGRESS] {percent}% - {message}")
    # FastAPI로 상태 전송
    # send_progress(self.job_id, percent, message)