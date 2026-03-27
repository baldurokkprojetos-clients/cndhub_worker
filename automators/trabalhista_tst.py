import logging
import time
import os
import base64
from pathlib import Path
from PIL import Image
from io import BytesIO
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.captcha_solver import solve_captcha_with_gemini
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from .base import BaseAutomator
from core.config import settings, get_chrome_major_version

logger = logging.getLogger(__name__)

class TrabalhistaTstAutomator(BaseAutomator):
    def execute(self) -> dict:
        logger.info(f"Iniciando emissão Trabalhista TST para CNPJ {self.cnpj}")
        download_dir = Path(self.get_download_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        cnpj_clean_path = ''.join(filter(str.isdigit, self.cnpj))
        file_path = os.path.join(download_dir, f"trabalhista_tst_{cnpj_clean_path}.pdf")
        
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
        if chrome_major:
            chrome_kwargs["version_main"] = chrome_major
        driver = uc.Chrome(**chrome_kwargs)
        
        try:
            url = "https://www.tst.jus.br/certidao1"
            logger.info(f"Acessando URL: {url}")
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            
            # Aceitar cookies
            try:
                cookie_btn = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="cookieEnabler"]/div[2]/a')))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cookie_btn)
                time.sleep(0.5)
                try:
                    cookie_btn.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", cookie_btn)
                time.sleep(0.5)
            except Exception as e:
                logger.info("Botão de cookies não encontrado ou já aceito.")
                
            time.sleep(2)
            
            # Check iframes - aguardar até que o iframe principal esteja disponível
            try:
                iframe = wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe")))
                driver.switch_to.frame(iframe)
                logger.info("Mudou para o iframe principal.")
            except Exception as e:
                logger.warning("Nenhum iframe encontrado ou erro ao mudar de frame.")
            
            # Clicar em Emitir Certidão Inicial
            try:
                btn_inicial = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="corpo"]/div/div[2]/input[1]')))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_inicial)
                time.sleep(0.5)
                try:
                    btn_inicial.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn_inicial)
                time.sleep(0.5)
            except Exception as e:
                logger.warning("Botão de emissão inicial não encontrado.")
            
            # Preencher CNPJ
            logger.info("Preenchendo CNPJ...")
            cnpj_input = wait.until(EC.presence_of_element_located((By.ID, "gerarCertidaoForm:cpfCnpj")))
            cnpj_input.clear()
            cnpj_input.send_keys(cnpj_clean_path)
            
            # Resolver Captcha via OCR
            logger.info("Aguardando imagem do captcha...")
            captcha_img_element = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="idImgBase64"]')))
            
            # Aguardar até que o src esteja presente e contenha base64
            src = ""
            for _ in range(10):
                src = captcha_img_element.get_attribute("src")
                if src and "base64," in src:
                    break
                time.sleep(0.5)

            if src and "base64," in src:
                base64_data = src.split("base64,")[1]
                image_data = base64.b64decode(base64_data)
                image = Image.open(BytesIO(image_data))
                
                # Executar OCR via Gemini
                captcha_text = solve_captcha_with_gemini(image)
                logger.info(f"Texto do captcha extraído via Gemini: {captcha_text}")
                
                if captcha_text:
                    captcha_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="idCampoResposta"]')))
                    captcha_input.clear()
                    captcha_input.send_keys(captcha_text)
                else:
                    logger.warning("OCR não retornou texto para o captcha.")
            else:
                logger.warning("Imagem de captcha não encontrada em formato base64.")
            
            # Mapear arquivos antes de clicar
            arquivos_antes = set(download_dir.glob("*.pdf"))

            # Clicar em Emitir
            try:
                btn_emitir = driver.find_element(By.NAME, "gerarCertidaoForm:btnEmitirCertidao")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_emitir)
                time.sleep(0.5)
                try:
                    btn_emitir.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn_emitir)
                time.sleep(5) # Aguardar processamento/download
            except Exception as e:
                logger.warning(f"Erro ao clicar em emitir: {e}")
            
            # Aguardando download ou imprimindo a tela de resposta
            logger.info("Aguardando download do arquivo PDF (se houver)...")
            baixou = False
            for _ in range(15):
                arquivos_agora = set(download_dir.glob("*.pdf"))
                arquivos_novos = arquivos_agora - arquivos_antes
                arquivos_finais = [f for f in arquivos_novos if not str(f).endswith(".crdownload")]
                if arquivos_finais:
                    arquivo_baixado = list(arquivos_finais)[0]
                    os.rename(arquivo_baixado, file_path)
                    baixou = True
                    break
                time.sleep(1)
                
            if not baixou:
                logger.warning("Download não detectado, salvando tela atual via CDP.")
                pdf = driver.execute_cdp_cmd("Page.printToPDF", {
                    "landscape": False,
                    "displayHeaderFooter": False,
                    "printBackground": True,
                    "preferCSSPageSize": True,
                })
                with open(file_path, "wb") as f:
                    f.write(base64.b64decode(pdf['data']))
                
            driver.quit()
            
            # Renomear e limpar antigos
            from datetime import datetime
            import glob
            data_atual = datetime.now().strftime("%Y%m%d")
            cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
            tipo = "trabalhista_tst"
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
            logger.error(f"Erro na emissão: {e}")
            try:
                driver.quit()
            except:
                pass
            return {
                "status": "error",
                "caminho_arquivo": None,
                "mensagem_erro": str(e)
            }
