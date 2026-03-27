import logging
import time
import os
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from .base import BaseAutomator
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.captcha_solver import solve_captcha_with_gemini
from core.config import settings, get_chrome_major_version, cleanup_uc_chromedriver_cache

logger = logging.getLogger(__name__)

class PrefeituraGoianiaAutomator(BaseAutomator):
    def execute(self) -> dict:
        logger.info(f"Iniciando emissão Prefeitura de Goiânia para CNPJ {self.cnpj}")
        download_dir = Path(self.get_download_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        cnpj_clean_path = ''.join(filter(str.isdigit, self.cnpj))
        file_path = os.path.join(download_dir, f"prefeitura_goiania_{cnpj_clean_path}.pdf")
        
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
            url = "https://www.goiania.go.gov.br/sistemas/sccer/asp/sccer00300f0.asp"
            logger.info(f"Acessando URL: {url}")
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            
            # 1 - Verificar se a página carregou corretamente
            try:
                wait.until(EC.presence_of_element_located((By.NAME, "sel_cpfcnpj")))
                logger.info("Página carregada com sucesso.")
            except Exception as e:
                raise Exception("Falha ao carregar a página da Prefeitura de Goiânia.")
            
            # Selecionar Tipo de Documento (CNPJ) primeiro
            select_doc = driver.find_element(By.NAME, "sel_cpfcnpj")
            # option[3] seria o CNPJ (1 é vazio, 2 é CPF, 3 é CNPJ, depende do select)
            opt_cnpj = select_doc.find_element(By.XPATH, "/html/body/font/form/table[1]/tbody/tr[1]/td[2]/select/option[3]")
            try:
                opt_cnpj.click()
            except Exception:
                driver.execute_script("arguments[0].click();", opt_cnpj)
            
            # Preencher CNPJ (apenas números pois o maxlength é 14)
            try:
                cnpj_input = wait.until(EC.presence_of_element_located((By.XPATH, "/html/body/font/form/table[1]/tbody/tr[1]/td[2]/input")))
            except Exception:
                # Fallback caso o XPath mude
                cnpj_input = wait.until(EC.presence_of_element_located((By.NAME, "txt_nr_cpfcnpj")))
            
            cnpj_input.clear()
            cnpj_input.send_keys(cnpj_clean_path)
            
            logger.info("Tentando resolver captcha com Gemini...")
            try:
                from PIL import Image
                import io

                # Capturar a imagem do captcha
                captcha_img_element = wait.until(EC.presence_of_element_located((By.ID, "id_img_captcha")))
                img_png = captcha_img_element.screenshot_as_png
                img = Image.open(io.BytesIO(img_png))
                
                # Extrair o texto com Gemini
                captcha_text = solve_captcha_with_gemini(img)
                
                logger.info(f"Texto do captcha extraído via Gemini: '{captcha_text}'")
                
                if captcha_text:
                    captcha_input = driver.find_element(By.ID, "id_txt_captcha")
                    captcha_input.clear()
                    captcha_input.send_keys(captcha_text)
                    time.sleep(1)
                else:
                    logger.warning("OCR não retornou texto, aguardando resolução manual...")
                    time.sleep(10)
            except Exception as e:
                logger.error(f"Erro ao resolver captcha com OCR: {e}")
                logger.info("Aguardando intervenção manual para o captcha...")
                time.sleep(10)
            
            # Clicar em Emitir
            try:
                emitir_btn = driver.find_element(By.XPATH, "/html/body/font/form/table[1]/tbody/tr[3]/td/input")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", emitir_btn)
                time.sleep(0.5)
                try:
                    emitir_btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", emitir_btn)
            except Exception as e:
                logger.warning(f"Erro ao clicar no botão emitir: {e}")
            
            # 2 e 3 - Verificar resultado da emissão (sucesso ou erro)
            logger.info("Verificando resultado da submissão do formulário...")
            time.sleep(3) # Aguardar carregamento da resposta
            
            # Verificar se ocorreu erro de CNPJ inválido
            try:
                error_msg_element = driver.find_elements(By.XPATH, "/html/body/form/table[3]/tbody/tr/td/b/font")
                if error_msg_element:
                    error_text = error_msg_element[0].text
                    if "NÚMERO DO CPF/CNPJ INVÁLIDO" in error_text.upper():
                        raise Exception("NÚMERO DO CPF/CNPJ INVÁLIDO ou não enviado no input.")
            except Exception as e:
                if "NÚMERO DO CPF/CNPJ INVÁLIDO" in str(e):
                    raise e
            
            # Verificar se a certidão foi gerada com sucesso (Prazo de Validade)
            try:
                success_element = wait.until(EC.presence_of_element_located((By.XPATH, "/html/body/form/table[3]/tbody/tr[2]/td")))
                if "Prazo de Validade" not in success_element.text:
                    # Tentar encontrar em qualquer lugar da página como fallback
                    if "Prazo de Validade" not in driver.page_source:
                        raise Exception("Não foi possível confirmar a geração da certidão (texto 'Prazo de Validade' não encontrado).")
            except Exception as e:
                if "Não foi possível confirmar" in str(e):
                    raise e
                # Fallback genérico caso o XPath falhe mas o texto exista
                if "Prazo de Validade" not in driver.page_source:
                    raise Exception("Falha na emissão da certidão ou captcha incorreto.")

            logger.info("Certidão gerada com sucesso na tela, prosseguindo com o download (PDF)...")
            
            # Executar impressão para PDF via CDP (DevTools Protocol)
            logger.info("Executando salvamento do arquivo (PDF via CDP)...")
            pdf = driver.execute_cdp_cmd("Page.printToPDF", {
                "landscape": False,
                "displayHeaderFooter": False,
                "printBackground": True,
                "preferCSSPageSize": True,
            })
            
            with open(file_path, "wb") as f:
                import base64
                f.write(base64.b64decode(pdf['data']))
                
            # Renomear e limpar antigos (Apenas do tipo prefeitura_goiania para este CNPJ específico)
            from datetime import datetime
            import glob
            data_atual = datetime.now().strftime("%Y%m%d")
            cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
            tipo = "prefeitura_goiania"
            final_file_name = f"{cnpj_clean}_{tipo}_{data_atual}.pdf"
            final_path = download_dir / final_file_name
            
            if os.path.exists(file_path):
                # Se o arquivo final já existe no destino, removemos para não dar erro no rename
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except:
                        pass
                os.rename(file_path, final_path)
                
            # Remover APENAS arquivos prefeitura_goiania do mesmo CNPJ antigos
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
            logger.error(f"[FALHA] Erro na emissão Prefeitura Goiânia: {e}", exc_info=True)
            return {
                "status": "error",
                "caminho_arquivo": None,
                "mensagem_erro": str(e)
            }
        finally:
            self.cleanup_driver(driver)
