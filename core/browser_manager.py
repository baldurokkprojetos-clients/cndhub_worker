from playwright.sync_api import sync_playwright
import logging

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Gerenciador do Browser Playwright seguindo a regra do project_standad.md:
    - Apenas 1 instância de browser por worker
    - Instanciação sob demanda (lazy loading)
    - Método para fechar instâncias ociosas (idle)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserManager, cls).__new__(cls)
            cls._instance._playwright = None
            cls._instance._browser = None
            cls._instance._context = None
        return cls._instance

    def _start_browser(self):
        if not self._playwright:
            self._playwright = sync_playwright().start()
        
        if not self._browser:
            logger.info("Iniciando instância única do Chromium...")
            # Headless configurável. Deixando False para debug inicial, mas em produção deve puxar de variável de ambiente.
            self._browser = self._playwright.chromium.launch(headless=False)
            self._context = self._browser.new_context(
                accept_downloads=True,
                viewport={"width": 1280, "height": 720}
            )

    def get_page(self):
        """Retorna uma nova página a partir do contexto único. Inicia o browser se não existir."""
        self._start_browser()
        return self._context.new_page()

    def close(self):
        """Fecha o browser e o playwright, garantindo que não fiquem processos órfãos."""
        if self._context:
            self._context.close()
            self._context = None
            
        if self._browser:
            logger.info("Fechando instância do Chromium...")
            self._browser.close()
            self._browser = None
            
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
            
    def is_running(self) -> bool:
        """Verifica se o browser está atualmente ativo."""
        return self._browser is not None

# Instância Singleton
browser_manager = BrowserManager()
