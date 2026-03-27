from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc
import logging
from pathlib import Path
import time
import os
import glob
from .base import BaseAutomator
from core.config import settings, get_chrome_major_version, cleanup_uc_chromedriver_cache

logger = logging.getLogger(__name__)

class ReceitaFederalAutomator(BaseAutomator):
    """
    Robô para a emissão de Certidão Negativa de Débitos (CND) da Receita Federal.
    URL Base: https://servicos.receitafederal.gov.br/servico/certidoes/#/home
    """
    
    def __init__(self, cliente_id: str, tipo_certidao_id: str, cnpj: str, **kwargs):
        super().__init__(cliente_id, tipo_certidao_id, cnpj, **kwargs)
        # Tenta pegar a URL dos kwargs (passada pelo worker a partir do banco), senão usa o default
        raw_url = kwargs.get("url", "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj")
        # Garante que a URL tem https://
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = "https://" + raw_url
        self.url = raw_url
        self.razao_social = kwargs.get("razao_social", "")
        
        # Seletores
        self.selectors = {
            "cookies_aceite": '//*[@id="card0"]/div/div[2]/button[2]',
            "link_inicial": '/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/app-informar-contribuinte/br-list/div/div[2]/div/a/div/div/span[2]',
            "input_cnpj": 'input[name="niContribuinte"]',
            "botao_emitir": '/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/app-coleta-parametros-pj/app-coleta-parametros-template/form/div[2]/div[2]/button[2]',
            "emitir_nova": '/html/body/modal-container/div[2]/div/div[3]/button[2]'
        }
        
    def execute(self) -> dict:
        logger.info(f"Iniciando automação da Receita Federal para CNPJ: {self.cnpj}")
        
        download_dir = Path(self.get_download_path())
        download_dir.mkdir(parents=True, exist_ok=True)
        
        options = uc.ChromeOptions()
        if settings.WORKER_HEADLESS:
            options.add_argument("--headless=new")
        
        # Configurar download path e desativar prompt
        prefs = {
            "download.default_directory": str(download_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True, # Faz download do pdf ao invés de abrir no navegador
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        options.add_experimental_option("prefs", prefs)
        
        # O Chrome crasha frequentemente se rodarmos múltiplos processos com a mesma pasta de perfil
        # A flag --no-sandbox pode ajudar na estabilidade
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-infobars")
        
        # Use um perfil isolado para o uc
        user_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "worker", "core", "uc_profile"))
        logger.info(f"Usando diretório de dados do Chrome (UC): {user_data_dir}")
        
        # Inicializa o webdriver do undetected_chromedriver
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
            logger.info(f"Acessando URL inicial: {self.url}")
            driver.get(self.url)
            time.sleep(3)
            
            # Como estamos usando um perfil existente que deve ter resolvido o captcha antes,
            # vamos pular a limpeza agressiva de cookies e localStorage, pois isso apagaria
            # os tokens de confiança do hCaptcha.
            logger.info("Mantendo cookies e storage locais para preservar confiança do hCaptcha.")
            
            wait = WebDriverWait(driver, 15)
            
            # 1. Aceitar cookies
            try:
                logger.info("Aguardando botão de cookies...")
                btn_cookies = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, self.selectors["cookies_aceite"]))
                )
                time.sleep(1)
                btn_cookies.click()
                logger.info("Cookies aceitos.")
            except TimeoutException:
                logger.info("Botão de cookies não encontrado ou já aceito.")
                
            time.sleep(2)
            
            # 2. Clicar no link inicial se existir
            try:
                logger.info("Aguardando link inicial...")
                btn_link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, self.selectors["link_inicial"]))
                )
                btn_link.click()
                logger.info("Link inicial clicado.")
            except TimeoutException:
                logger.info("Link inicial não encontrado, assumindo que já está na tela de CNPJ.")
                
            # 3. Preencher CNPJ
            cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
            logger.info(f"Preenchendo CNPJ: {cnpj_clean}")
            
            try:
                input_cnpj = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, self.selectors["input_cnpj"]))
                )
                time.sleep(2)
                
                # Scroll para o elemento para evitar que barras superiores/inferiores o cubram
                driver.execute_script("arguments[0].scrollIntoView(true);", input_cnpj)
                time.sleep(1)
                
                try:
                    input_cnpj.clear()
                    input_cnpj.send_keys(cnpj_clean)
                except Exception as interact_err:
                    logger.warning(f"Falha ao interagir normalmente ({interact_err}), tentando via JavaScript...")
                    driver.execute_script(f"arguments[0].value = '{cnpj_clean}';", input_cnpj)
                    # Disparar eventos de input e change para o Angular/React reconhecer a mudança
                    driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", input_cnpj)
                    driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", input_cnpj)
                    
                logger.info("CNPJ preenchido.")
            except TimeoutException:
                logger.error("Campo de CNPJ não encontrado.")
                raise
                
            # 4. Clicar em Emitir
            logger.info("Clicando em emitir...")
            time.sleep(1)
            
            try:
                btn_emitir = wait.until(
                    EC.element_to_be_clickable((By.XPATH, self.selectors["botao_emitir"]))
                )
                
                # Conta os arquivos PDF antes de clicar
                arquivos_antes = set(glob.glob(str(download_dir / "*.pdf")))
                
                # Limpa arquivos .crdownload antigos que podem travar o loop
                for old_cr in glob.glob(str(download_dir / "*.crdownload")) + glob.glob(str(download_dir / "*.tmp")):
                    try:
                        os.remove(old_cr)
                    except Exception:
                        pass
                
                # Executa click via script para evitar "Element is not clickable at point"
                driver.execute_script("arguments[0].click();", btn_emitir)
                
                logger.info("Aguardando processamento (spinner) / reCAPTCHA invisivel...")
                time.sleep(5)
                
                # Trata explicitamente o caso de mensagem "Não foi possível concluir a ação" logo após clicar em emitir
                try:
                    modal_body = driver.find_element(By.TAG_NAME, "modal-container").text
                    if "Não foi possível" in modal_body or "Erro" in modal_body or "Aviso" in modal_body:
                        logger.error(f"Mensagem de erro detectada na página logo após emissão: {modal_body}")
                        # Se for o erro "023 - Não foi possível", a gente retorna falha pra tentar dnv
                        return {
                            "status": "error",
                            "caminho_arquivo": None,
                            "mensagem_erro": f"Site da Receita retornou erro: {modal_body.replace(chr(10), ' ')}"
                        }
                except NoSuchElementException:
                    pass
                
                # Verifica mensagens de erro na página (não modal)
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    if "insuficientes para emitir a certidão pela Internet" in body_text:
                        logger.error("Aviso da Receita: Informações insuficientes para emitir a certidão pela Internet.")
                        return {
                            "status": "error",
                            "caminho_arquivo": None,
                            "mensagem_erro": "As informações disponíveis na Receita Federal são insuficientes para emitir a certidão pela Internet."
                        }
                except NoSuchElementException:
                    pass
                    
                # 6. Verificar se existe o modal de "Emitir Nova" e clicar
                try:
                    btn_nova = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, self.selectors["emitir_nova"]))
                    )
                    logger.info("Modal de 'Emitir Nova' detectado. Clicando...")
                    driver.execute_script("arguments[0].click();", btn_nova)
                except TimeoutException:
                    logger.info("Modal de 'Emitir Nova' não apareceu.")
                
                # Esperar processamento / download
                logger.info("Aguardando processamento e download do PDF...")
                timeout_download = 60
                arquivo_novo = None
                link_clicado = False
                
                start_time = time.time()
                while time.time() - start_time < timeout_download:
                    # 1. Verifica se há alerta de erro
                    try:
                        alert = driver.find_element(By.XPATH, '//*[@id="alert-content"]')
                        if alert.is_displayed():
                            alert_text = alert.text.strip()
                            if alert_text:
                                logger.error(f"Alerta detectado: {alert_text}")
                                return {
                                    "status": "error",
                                    "caminho_arquivo": None,
                                    "mensagem_erro": f"Receita Federal retornou alerta: {alert_text}"
                                }
                    except Exception:
                        pass

                    # 2. Verifica se a página de resultado de erro apareceu
                    try:
                        # XPath para o texto de erro na página de resultado
                        erro_p = driver.find_element(By.XPATH, '/html/body/app-root/mf-portal-layout/portal-main-layout/div/main/ng-component/ng-component/app-resultado-certidao/div[2]/div/div/p')
                        
                        # Se achou o parágrafo, verifica se NÃO tem o link de download dentro dele
                        # Porque se tiver o link de download (<a>), é sucesso.
                        try:
                            link = erro_p.find_element(By.XPATH, './a')
                            # A Receita Federal faz o auto-download. Só clicamos no link se demorar muito
                            if not link_clicado and (time.time() - start_time > 10):
                                try:
                                    logger.info("Link de download encontrado e auto-download demorou. Clicando para garantir...")
                                    driver.execute_script("arguments[0].click();", link)
                                    link_clicado = True
                                    time.sleep(2)
                                except Exception as click_err:
                                    logger.warning(f"Não foi possível clicar no link de download: {click_err}")
                            # Continua aguardando o download do arquivo
                        except Exception:
                            # Se não achou o link, então o texto do parágrafo pode ser um erro ou mensagem de carregamento
                            erro_text = erro_p.text.strip()
                            if erro_text:
                                # Ignora se for mensagem de carregamento
                                if "Estamos analisando seu pedido" in erro_text or "Aguarde" in erro_text:
                                    pass
                                else:
                                    logger.error(f"Erro na página de resultado: {erro_text}")
                                    return {
                                        "status": "error",
                                        "caminho_arquivo": None,
                                        "mensagem_erro": f"Erro na emissão: {erro_text}"
                                    }
                    except Exception:
                        pass
                        
                    # Verifica mensagens genéricas de erro (ex: modal)
                    try:
                        # try to find modal-container, but don't crash if session disconnected
                        try:
                            modal_body = driver.find_element(By.TAG_NAME, "modal-container").text
                            if "Não foi possível" in modal_body or "Erro" in modal_body or "Aviso" in modal_body:
                                logger.error(f"Mensagem de erro detectada na página: {modal_body}")
                                return {
                                    "status": "error",
                                    "caminho_arquivo": None,
                                    "mensagem_erro": f"Site da Receita retornou erro: {modal_body.replace(chr(10), ' ')}"
                                }
                        except Exception:
                            pass

                        # Try to detect if hCaptcha challenged appeared
                        try:
                            iframes = driver.find_elements(By.TAG_NAME, "iframe")
                            for iframe in iframes:
                                if "hcaptcha" in iframe.get_attribute("src").lower():
                                    if iframe.is_displayed():
                                        logger.warning("hCaptcha visual detectado na tela!")
                        except Exception:
                            pass

                    except Exception as loop_e:
                        pass # Silencia erros de DOM para não quebrar a espera do download

                    arquivos_depois = set(glob.glob(str(download_dir / "*.pdf")))
                    novos_arquivos = arquivos_depois - arquivos_antes
                    
                    # Ignorar arquivos .crdownload e .tmp que pertençam APENAS a este processo (se possível, mas globalmente para simplificar)
                    arquivos_crdownload = set(glob.glob(str(download_dir / "*.crdownload"))) | set(glob.glob(str(download_dir / "*.tmp")))
                    
                    if novos_arquivos:
                        arquivo_novo = list(novos_arquivos)[0]
                        logger.info(f"Arquivo PDF detectado e download concluído: {arquivo_novo}")
                        break
                    
                    if arquivos_crdownload:
                        logger.info(f"Aguardando download finalizar (arquivos temporários detectados: {len(arquivos_crdownload)})...")
                        
                    time.sleep(2)
                    
                if not arquivo_novo:
                    # Tira screenshot para debug
                    debug_path = str(download_dir / f"debug_rf_nodownload_{int(time.time())}.png")
                    driver.save_screenshot(debug_path)
                    logger.info(f"Screenshot de erro salvo em: {debug_path}")
                    
                    # Log de arquivos na pasta
                    arquivos_atuais = os.listdir(str(download_dir))
                    logger.info(f"Arquivos presentes na pasta de download: {arquivos_atuais}")
                    
                    # Loga o texto da pagina para sabermos se tem erro
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    logger.info(f"Texto da página no momento do erro: {body_text[:1000]}") # 1000 chars is enough
                    
                    raise Exception("Nenhum arquivo PDF foi salvo após o processamento.")
                    
                # Renomear para o padrão: {cnpj}_{tipo}_{data}.pdf
                from datetime import datetime
                data_atual = datetime.now().strftime("%Y%m%d")
                cnpj_clean = ''.join(filter(str.isdigit, self.cnpj))
                tipo = "receita"
                file_name = f"{cnpj_clean}_{tipo}_{data_atual}.pdf"
                
                download_path = download_dir / file_name
                
                if arquivo_novo and os.path.exists(arquivo_novo):
                    if os.path.exists(download_path):
                        try:
                            os.remove(download_path)
                        except:
                            pass
                    os.rename(arquivo_novo, download_path)
                    
                    # Se houve múltiplos downloads (duplicatas), limpar os extras
                    for extra_file in novos_arquivos:
                        if extra_file != arquivo_novo and os.path.exists(extra_file):
                            try:
                                os.remove(extra_file)
                                logger.info(f"Arquivo duplicado removido: {extra_file}")
                            except Exception as e:
                                pass
                
                # Deletar todos os arquivos antigos do mesmo tipo para este CNPJ (mesmo de outras datas)
                old_files_pattern = str(download_dir / f"{cnpj_clean}_{tipo}_*.pdf")
                for old_file in glob.glob(old_files_pattern):
                    if os.path.exists(old_file) and str(old_file) != str(download_path):
                        try:
                            os.remove(old_file)
                            logger.info(f"Arquivo antigo removido: {old_file}")
                        except Exception as e:
                            logger.warning(f"Não foi possível apagar o arquivo antigo {old_file}: {e}")
                    
                logger.info(f"Automação concluída com sucesso. Arquivo: {download_path}")
                
                return {
                    "status": "completed",
                    "caminho_arquivo": str(download_path),
                    "mensagem_erro": None
                }
                
            except TimeoutException as e:
                logger.error(f"Timeout ao clicar em emitir: {str(e)}")
                raise
                
        except Exception as e:
            logger.error(f"Erro inesperado no automador: {str(e)}")
            return {
                "status": "error",
                "caminho_arquivo": None,
                "mensagem_erro": f"Erro interno: {str(e)}"
            }
        finally:
            driver.quit()

    def _solve_captcha(self, page):
        pass
