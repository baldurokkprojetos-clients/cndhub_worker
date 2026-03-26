import os
from dotenv import load_dotenv

load_dotenv()

class WorkerSettings:
    API_BASE_URL = os.getenv("API_BASE_URL") or os.getenv("BACKEND_URL", "http://localhost:8001")
    HUB_API_KEY = os.getenv("HUB_API_KEY", "")
    WORKER_ID = os.getenv("WORKER_ID", "default-worker-01")
    POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", 1))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
    BASE_CERTIDOES_PATH = os.getenv("BASE_CERTIDOES_PATH", "C:/CERTIDOES")
    MAX_CONCURRENT_BROWSERS = int(os.getenv("MAX_CONCURRENT_BROWSERS", 1))
    WORKER_HEADLESS = os.getenv("WORKER_HEADLESS", "false").strip().lower() in ("1", "true", "yes", "on")
    BROWSER_IDLE_TIMEOUT_MINUTES = 5

settings = WorkerSettings()
