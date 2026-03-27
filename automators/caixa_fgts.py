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

class CaixaFgtsAutomator(BaseAutomator):
    def execute(self) -> dict:
        logger.info(f"Iniciando emissão Caixa FGTS para CNPJ {self.cnpj}")
        download_dir = Path(self.get_download_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        cnpj_clean_path = ''.join(filter(str.isdigit, self.cnpj))
        file_path = os.path.join(download_dir, f"caixa_fgts_{cnpj_clean_path}.pdf")
        
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
            url = "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf"
            logger.info(f"Acessando URL: {url}")
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            
            # Preencher CNPJ (limpo, sem pontuações)
            logger.info(f"Tentando preencher o CNPJ. Valor limpo a ser enviado: '{cnpj_clean_path}' (Tamanho: {len(cnpj_clean_path)})")
            
            try:
                # O usuário solicitou usar o XPath //*[@id="mainForm:txtInscricao1"]
                cnpj_input = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="mainForm:txtInscricao1"]')))
                cnpj_input.clear()
                # Enviar o CNPJ limpo sem caracteres especiais
                cnpj_input.send_keys(cnpj_clean_path)
                logger.info(f"CNPJ enviado ao input com sucesso. Valor enviado: {cnpj_clean_path}")
            except Exception as e:
                logger.error(f"Erro ao enviar CNPJ ao input: {str(e)}")
                raise Exception(f"Falha ao enviar CNPJ ao input: {str(e)}")
            
            # Selecionar UF (GO)
            uf_select = driver.find_element(By.ID, "mainForm:uf")
            uf_select.click()
            time.sleep(0.5)
            uf_select.find_element(By.XPATH, "//option[@value='GO']").click()
            
            # Consultar
            btn_consultar = driver.find_element(By.ID, "mainForm:btnConsultar")
            btn_consultar.click()
            
            time.sleep(2)
            
            # Verificar se houve erro de CNPJ ou se está regular
            try:
                msg_element = driver.find_elements(By.XPATH, "//*[@id='mainForm']/div[1]/span")
                if msg_element:
                    msg_text = msg_element[0].text
                    if "Inscrição: informar o CNPJ correto" in msg_text:
                        raise Exception("Inscrição: informar o CNPJ correto (CNPJ Inválido).")
            except Exception as e:
                if "CNPJ Inválido" in str(e):
                    raise e
            
            # Verificar se a empresa está regular
            try:
                regular_element = driver.find_elements(By.XPATH, "//*[contains(text(), 'A EMPRESA abaixo identificada está REGULAR perante o FGTS:')]")
                if not regular_element:
                    # Fallback procurando em todo o HTML
                    if "A EMPRESA abaixo identificada está REGULAR perante o FGTS:" not in driver.page_source:
                        raise Exception("A empresa não está regular perante o FGTS ou a página não carregou corretamente.")
            except Exception as e:
                if "não está regular" in str(e):
                    raise e
            
            logger.info("Empresa validada e REGULAR perante o FGTS, prosseguindo...")
            
            # Ações sequenciais com waits
            try:
                # Resultado
                span_resultado = wait.until(EC.presence_of_element_located((By.XPATH, "//*[@id='mainForm']/div[1]/div/span")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", span_resultado)
                time.sleep(0.5)
                try:
                    span_resultado.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", span_resultado)
                time.sleep(0.5)
                
                # J_ID51
                btn_jid = driver.find_element(By.ID, "mainForm:j_id51")
                try:
                    btn_jid.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn_jid)
                time.sleep(0.5)
                
                # Visualizar
                btn_visualizar = driver.find_element(By.NAME, "mainForm:btnVisualizar")
                try:
                    btn_visualizar.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn_visualizar)
                
                # Verificar se a certidão final foi gerada ("Certificação Número:")
                logger.info("Aguardando carregamento da tela da certidão...")
                certidao_carregada = False
                for _ in range(15):
                    if "Certificação Número:" in driver.page_source:
                        certidao_carregada = True
                        break
                    time.sleep(1)
                
                if not certidao_carregada:
                    raise Exception("Não foi possível confirmar a emissão da certidão (texto 'Certificação Número:' não encontrado na tela final após 15 segundos).")
                
                logger.info("Certidão gerada e validada na tela final, prosseguindo com a impressão via CDP...")
                
                # NÃO clicar em Imprimir pois isso invoca a caixa de diálogo da impressora (XPS)
                # Vamos usar o Page.printToPDF direto nesta tela de visualização
            except Exception as e:
                logger.warning(f"Erro em passo intermediário do FGTS: {e}")
                raise Exception(f"Falha ao visualizar a certidão: {e}")
            
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
            
            baixou = os.path.exists(file_path)
            
            if not baixou:
                raise Exception("Falha ao salvar/baixar o arquivo PDF da certidão.")
            
            # Renomear e limpar antigos (Apenas do tipo FGTS para este CNPJ específico)
            from datetime import datetime
            import glob
            data_atual = datetime.now().strftime("%Y%m%d")
            cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
            tipo = "fgts"
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
                
            # Remover APENAS arquivos FGTS do mesmo CNPJ (antigos)
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
            logger.error(f"[FALHA] Erro na emissão Caixa FGTS: {e}", exc_info=True)
            return {
                "status": "error",
                "caminho_arquivo": None,
                "mensagem_erro": str(e)
            }
        finally:
            self.cleanup_driver(driver)
