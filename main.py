import time
import requests
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("worker_main")

API_BASE_URL = settings.API_BASE_URL
HUB_API_KEY = settings.HUB_API_KEY

def get_headers():
    headers = {"X-API-Key": HUB_API_KEY}
    if settings.WORKER_ID:
        headers["X-Worker-Id"] = settings.WORKER_ID
    return headers

def kill_chromedriver_processes():
    """Mata todos os processos do chromedriver e chrome pendentes (para servidores independentes)."""
    try:
        if os.name == 'nt':
            os.system("taskkill /f /im chromedriver.exe >nul 2>&1")
            os.system("taskkill /f /im chrome.exe >nul 2>&1")
        else:
            os.system("pkill -f chromedriver > /dev/null 2>&1")
            os.system("pkill -f chrome > /dev/null 2>&1")
    except Exception as e:
        logger.error(f"Erro ao matar processos do chromedriver: {e}")

def get_pending_jobs():
    """Busca jobs pendentes na API do Backend."""
    url = f"{API_BASE_URL}/api/v1/jobs/pending"
    try:
        limit = max(5, settings.MAX_CONCURRENT_BROWSERS)
        response = requests.get(url, params={"limit": limit}, headers=get_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        status = getattr(e.response, "status_code", None)
        body = getattr(e.response, "text", None)
        logger.error(f"Erro ao buscar jobs pendentes na API: {e} | status={status} | body={body}")
        return []

def update_job_status(job_id, status, error_msg=None):
    """Atualiza o status do job na API do Backend."""
    url = f"{API_BASE_URL}/api/v1/jobs/{job_id}/status"
    try:
        payload = {"status": status}
        if error_msg:
            payload["mensagem_erro"] = error_msg
        response = requests.post(url, json=payload, headers=get_headers(), timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        status_code = getattr(e.response, "status_code", None)
        body = getattr(e.response, "text", None)
        logger.error(f"Erro ao atualizar status do job {job_id}: {e} | status={status_code} | body={body}")
        return False

def update_certidao_via_api(cliente_id, tipo_certidao_id, status, file_path=None, error_msg=None):
    """Envia o resultado (Upsert da Certidão) para a API do Backend."""
    url = f"{API_BASE_URL}/api/v1/certidoes/upsert"
    
    # multipart/form-data expected by the backend
    data = {
        "cliente_id": str(cliente_id),
        "tipo_certidao_id": str(tipo_certidao_id),
        "status": status,
    }
    
    if error_msg:
        data["mensagem_erro"] = error_msg
        
    files = None
    if file_path and os.path.exists(file_path):
        # We don't send the local absolute path string anymore, we send the file content
        files = {"file": open(file_path, "rb")}
        
    try:
        response = requests.post(url, data=data, files=files, headers=get_headers())
        response.raise_for_status()
        logger.info(f"Certidão atualizada na API com sucesso. Status: {status}")
        return True
    except requests.RequestException as e:
        logger.error(f"Erro ao chamar API de upsert da certidão: {e}")
        return False
    finally:
        if files:
            files["file"].close()

def process_job(job):
    job_id = job["job_id"]
    logger.info(f"Processando Job ID: {job_id} | Tipo: {job['tipo']}")
    
    try:
        automator_module = job["automator_module"]
        logger.info(f"Iniciando automação módulo: {automator_module} para CNPJ {job.get('cnpj')}")
        
        # 1. Instanciar o Robô
        from automators import get_automator
        automator = get_automator(
            module_name=automator_module,
            cliente_id=job["cliente_id"],
            tipo_certidao_id=job["tipo_certidao_id"],
            cnpj=job["cnpj"],
            razao_social=job.get("razao_social", ""),
            url=job.get("url")
        )
        
        # 2. Executar o Robô
        result = automator.execute()
        
        # 3. Atualizar a Certidão no Backend
        update_success = update_certidao_via_api(
            cliente_id=job["cliente_id"],
            tipo_certidao_id=job["tipo_certidao_id"],
            status=result["status"],
            file_path=result.get("caminho_arquivo"),
            error_msg=result.get("mensagem_erro")
        )
        
        # 4. Atualizar o status do Job
        if update_success and result["status"] == "completed":
            update_job_status(job_id, "completed")
        else:
            update_job_status(job_id, "error", error_msg=result.get("mensagem_erro"))
            
    except Exception as e:
        logger.error(f"[FALHA] Erro ao processar job {job_id}: {e}", exc_info=True)
        update_job_status(job_id, "error", error_msg=str(e))
    finally:
        if settings.MAX_CONCURRENT_BROWSERS <= 1:
            kill_chromedriver_processes()

def worker_loop():
    logger.info("Iniciando Worker RPA Independente...")
    logger.info(f"Conectado ao Backend em: {API_BASE_URL}")
    
    while True:
        jobs = get_pending_jobs()
        if jobs:
            logger.info(f"Encontrados {len(jobs)} jobs pendentes.")
            max_workers = max(1, settings.MAX_CONCURRENT_BROWSERS)
            if max_workers <= 1:
                for job in jobs:
                    process_job(job)
            else:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(process_job, job) for job in jobs[:max_workers]]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"[FALHA] Execução paralela do job: {e}", exc_info=True)
        else:
            logger.debug("Nenhum job pendente. Aguardando...")
            
        time.sleep(settings.POLLING_INTERVAL)

if __name__ == "__main__":
    worker_loop()
