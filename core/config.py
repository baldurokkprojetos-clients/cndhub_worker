import os
import re
import subprocess
from dotenv import load_dotenv

try:
    import winreg
except ImportError:
    winreg = None

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

def get_chrome_major_version() -> int | None:
    env_version = os.getenv("CHROME_VERSION_MAIN")
    if env_version and env_version.isdigit():
        return int(env_version)
    version = None
    if winreg:
        registry_keys = [
            (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon")
        ]
        for hive, path in registry_keys:
            try:
                with winreg.OpenKey(hive, path) as key:
                    version, _ = winreg.QueryValueEx(key, "version")
                    break
            except OSError:
                continue
    if not version:
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
        ]
        for chrome_path in chrome_paths:
            if os.path.exists(chrome_path):
                try:
                    result = subprocess.run([chrome_path, "--version"], capture_output=True, text=True, check=False)
                    version = result.stdout.strip() or result.stderr.strip()
                    if version:
                        break
                except Exception:
                    continue
    if not version:
        for command in (["chrome", "--version"], ["google-chrome", "--version"], ["chromium", "--version"], ["chromium-browser", "--version"]):
            try:
                result = subprocess.run(command, capture_output=True, text=True, check=False)
                version = result.stdout.strip() or result.stderr.strip()
                if version:
                    break
            except Exception:
                continue
    if not version:
        return None
    match = re.search(r"(\d+)\.", version)
    if not match:
        return None
    return int(match.group(1))
