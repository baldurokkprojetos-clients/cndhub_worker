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

class ProjudiGoiasAutomator(BaseAutomator):
    def execute(self) -> dict:
        logger.info(f"Iniciando emissão Projudi GO para CNPJ {self.cnpj}")
        download_dir = Path(self.get_download_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        cnpj_clean_path = ''.join(filter(str.isdigit, self.cnpj))
        file_path = os.path.join(download_dir, f"projudi_goias_{cnpj_clean_path}.pdf")
        
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
        
        user_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "worker", "core", "uc_profile_projudi"))
        
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
            url = "https://projudi.tjgo.jus.br/CertidaoSegundoGrauNegativaPositivaPublicaPJ?PaginaAtual=1"
            logger.info(f"Acessando URL: {url}")
            driver.get(url)
            
            # Aguardar 10s após abrir o site (Cloudflare)
            logger.info("Aguardando 10s (Cloudflare)...")
            time.sleep(10)
            
            wait = WebDriverWait(driver, 15)
            
            # 1. Preencher Razão Social
            razao_social = self.kwargs.get('razao_social', '')
            logger.info(f"[Projudi - Passo 1] Preenchendo Razão Social: {razao_social}")
            try:
                rs_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="RazaoSocial"]')))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", rs_input)
                rs_input.clear()
                rs_input.send_keys(razao_social)
            except Exception as e:
                logger.error(f"[Projudi - Erro no Passo 1] Falha ao preencher razão social: {e}", exc_info=True)
            
            # 2. Preencher CNPJ (Limpo, sem pontuação)
            logger.info(f"[Projudi - Passo 2] Preenchendo CNPJ: {cnpj_clean_path}")
            try:
                cnpj_input = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="Cnpj"]')))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cnpj_input)
                cnpj_input.clear()
                cnpj_input.send_keys(cnpj_clean_path)
            except Exception as e:
                logger.error(f"[Projudi - Erro no Passo 2] Falha ao preencher CNPJ: {e}", exc_info=True)

            # 3. Selecionar o Radio Tipo Área (Cível)
            logger.info("[Projudi - Passo 3] Selecionando a área (Cível)...")
            try:
                radio_area = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="divEditar"]/fieldset[1]/div[4]/input[1]')))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", radio_area)
                try:
                    radio_area.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", radio_area)
            except Exception as e:
                logger.error(f"[Projudi - Erro no Passo 3] Falha ao clicar no radio de área: {e}", exc_info=True)

            # Aguardar 1s após interações
            time.sleep(1)

            # Mapear arquivos antes de clicar
            arquivos_antes = set(download_dir.glob("*.*"))

            # Aguardar 1s após interações
            time.sleep(1)

            # 4. Clicar no botão para emitir
            logger.info("[Projudi - Passo 4] Clicando no botão Emitir...")
            url_antes_click = driver.current_url
            try:
                btn_emitir = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="divBotoesCentralizados"]/input[1]')))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_emitir)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", btn_emitir)
            except Exception as e:
                logger.error(f"[Projudi - Erro no Passo 4] Falha ao clicar no botão de emitir: {e}", exc_info=True)
            
            # 5. Aguardar carregamento da certidão
            logger.info("[Projudi - Passo 5] Aguardando emissão da certidão e início do download...")
            
            try:
                # Aguarda 5 segundos conforme solicitado
                time.sleep(5)
                
                # Verifica diálogo de erro de CNPJ inválido
                try:
                    dialogs = driver.find_elements(By.XPATH, '//*[@id="dialog"]')
                    for dialog in dialogs:
                        if dialog.is_displayed() and "CNPJ inválido" in dialog.text:
                            logger.error("Cnpj Invalido")
                            return {
                                "status": "error",
                                "mensagem_erro": "Cnpj Invalido"
                            }
                except Exception:
                    pass

                # Aguardar download do arquivo
                logger.info("Aguardando download do arquivo PDF...")
                arquivo_baixado = None
                for _ in range(45): # Aumentado para 45s para garantir tempo de geração
                    arquivos_depois = set(download_dir.glob("*.*"))
                    novos_arquivos = arquivos_depois - arquivos_antes
                    
                    if novos_arquivos:
                        for arq in novos_arquivos:
                            if not str(arq).endswith(".crdownload") and not str(arq).endswith(".tmp"):
                                arquivo_baixado = arq
                                break
                    if arquivo_baixado:
                        break
                    time.sleep(1)
                
                if not arquivo_baixado:
                    raise Exception("Tempo esgotado: O download do arquivo não foi concluído.")
                
                logger.info(f"PDF baixado identificado em: {arquivo_baixado}")
                file_path = str(arquivo_baixado)
                    
            except Exception as e:
                logger.warning(f"Erro ao aguardar estado final da página: {e}")
                raise Exception(f"Não foi possível gerar a certidão. Detalhes: {str(e)}")
            
            # Renomear e limpar antigos
            from datetime import datetime
            import glob
            data_atual = datetime.now().strftime("%Y%m%d")
            cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
            tipo = "projudi_goias"
            final_file_name = f"{cnpj_clean}_{tipo}_{data_atual}.pdf"
            final_path = download_dir / final_file_name
            
            # Deletar arquivos antigos APENAS deste tipo e CNPJ
            old_files_pattern = str(download_dir / f"{cnpj_clean}_{tipo}_*.pdf")
            for old_file in glob.glob(old_files_pattern):
                if os.path.exists(old_file) and str(old_file) != str(final_path):
                    try:
                        os.remove(old_file)
                        logger.info(f"Arquivo antigo removido: {old_file}")
                    except Exception as e:
                        logger.warning(f"Não foi possível apagar o arquivo antigo {old_file}: {e}")
            
            # Movendo arquivo_baixado/file_path para final_path
            if os.path.exists(file_path):
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception as e:
                        logger.warning(f"Não foi possível remover arquivo existente antes de renomear: {e}")
                
                try:
                    os.rename(file_path, final_path)
                    logger.info(f"Certidão renomeada para: {final_path}")
                except Exception as e:
                    import shutil
                    shutil.copy2(file_path, final_path)
                    os.remove(file_path)
                    logger.info(f"Certidão copiada e renomeada para: {final_path}")
            
            return {
                "status": "completed",
                "caminho_arquivo": str(final_path),
                "mensagem_erro": None
            }
        except Exception as e:
            logger.error(f"[FALHA] Projudi GO - Exceção capturada no bloco principal: {e}", exc_info=True)
            return {
                "status": "error",
                "caminho_arquivo": None,
                "mensagem_erro": str(e)
            }
        finally:
            self.cleanup_driver(driver)
