import logging
import time
import os
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from .base import BaseAutomator
from core.config import settings, get_chrome_major_version, cleanup_uc_chromedriver_cache

logger = logging.getLogger(__name__)

class SefazGoiasAutomator(BaseAutomator):
    def execute(self) -> dict:
        logger.info(f"Iniciando emissão Sefaz GO para CNPJ {self.cnpj}")
        download_dir = Path(self.get_download_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        cnpj_clean_path = ''.join(filter(str.isdigit, self.cnpj))
        file_path = os.path.join(download_dir, f"sefaz_goias_{cnpj_clean_path}.pdf")
        
        options = uc.ChromeOptions()
        prefs = {
            "download.default_directory": str(download_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        }
        options.add_experimental_option("prefs", prefs)
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if settings.WORKER_HEADLESS:
            options.add_argument("--headless=new")
        
        user_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "worker", "core", "uc_profile"))
        
        chrome_kwargs = {
            "options": options,
            "user_data_dir": user_data_dir
        }
        chrome_major = get_chrome_major_version()
        cleanup_uc_chromedriver_cache(chrome_major)
        if chrome_major:
            chrome_kwargs["version_main"] = chrome_major
        driver = uc.Chrome(**chrome_kwargs)
        
        try:
            url = "https://www.sefaz.go.gov.br/Certidao/Emissao/"
            logger.info(f"Acessando URL: {url}")
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            
            # Tipo Documento CNPJ
            try:
                tipo_doc = wait.until(EC.presence_of_element_located((By.ID, "Certidao.TipoDocumentoCNPJ")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tipo_doc)
                time.sleep(0.5)
                try:
                    tipo_doc.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", tipo_doc)
            except Exception as e:
                logger.warning(f"Erro ao selecionar tipo documento CNPJ: {e}")
            
            # Preencher CNPJ
            cnpj_input = wait.until(EC.presence_of_element_located((By.ID, "Certidao.NumeroDocumentoCNPJ")))
            cnpj_input.send_keys(self.cnpj)
            
            # Mapear arquivos antes de clicar
            arquivos_antes = set(download_dir.glob("*.*"))

            # Clicar em Emitir
            try:
                btn_emitir = driver.find_element(By.XPATH, '//*[@id="form1"]/div/div[2]/input[1]')
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_emitir)
                time.sleep(0.5)
                try:
                    btn_emitir.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn_emitir)
            except Exception as e:
                logger.warning(f"Erro ao clicar em emitir: {e}")
            
            # Aguardando download do arquivo (que vem como certidao.asp mas é PDF)
            logger.info("Aguardando download do arquivo gerado...")
            baixou = False
            for _ in range(45):
                arquivos_agora = set(download_dir.glob("*.*"))
                arquivos_novos = arquivos_agora - arquivos_antes
                arquivos_finais = [f for f in arquivos_novos if not str(f).endswith(".crdownload")]
                if arquivos_finais:
                    arquivo_baixado = list(arquivos_finais)[0]
                    # Renomeia para o caminho final (forçando ser PDF)
                    os.rename(arquivo_baixado, file_path)
                    baixou = True
                    break
                time.sleep(1)
                
            if not baixou:
                raise Exception("Tempo limite excedido aguardando o download da certidão.")
            
            # Renomear e limpar antigos
            from datetime import datetime
            import glob
            data_atual = datetime.now().strftime("%Y%m%d")
            cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
            tipo = "sefaz_goias"
            final_file_name = f"{cnpj_clean}_{tipo}_{data_atual}.pdf"
            final_path = download_dir / final_file_name
            
            if os.path.exists(file_path):
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except:
                        pass
                os.rename(file_path, final_path)
            
            # Deletar arquivos antigos APENAS deste tipo e CNPJ
            old_files_pattern = str(download_dir / f"{cnpj_clean}_{tipo}_*.pdf")
            for old_file in glob.glob(old_files_pattern):
                if os.path.exists(old_file) and str(old_file) != str(final_path):
                    try:
                        os.remove(old_file)
                        logger.info(f"Arquivo antigo removido: {old_file}")
                    except Exception as e:
                        logger.warning(f"Não foi possível apagar o arquivo antigo {old_file}: {e}")
            
            return {
                "status": "completed",
                "caminho_arquivo": str(final_path),
                "mensagem_erro": None
            }
        except Exception as e:
            logger.error(f"[FALHA] Erro na emissão Sefaz GO: {e}", exc_info=True)
            return {
                "status": "error",
                "caminho_arquivo": None,
                "mensagem_erro": str(e)
            }
        finally:
            self.cleanup_driver(driver)
