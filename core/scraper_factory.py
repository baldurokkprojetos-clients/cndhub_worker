import importlib
import logging

logger = logging.getLogger(__name__)

class ScraperFactory:
    """
    Factory responsável por instanciar dinamicamente o scraper correto
    baseado no 'scraper_module' definido no banco de dados.
    """
    
    @staticmethod
    def get_scraper(scraper_module_name: str):
        """
        Importa o módulo dinamicamente de `worker.scrapers.{scraper_module_name}`
        """
        try:
            # Importa o módulo (ex: worker.scrapers.receita_federal)
            module = importlib.import_module(f"scrapers.{scraper_module_name}")
            
            # Esperamos que cada módulo scraper tenha uma classe base chamada Scraper
            scraper_class = getattr(module, "Scraper")
            return scraper_class()
            
        except ImportError as e:
            logger.error(f"Erro ao importar o scraper '{scraper_module_name}': {e}")
            raise ValueError(f"Scraper module '{scraper_module_name}' não encontrado.")
        except AttributeError:
            logger.error(f"O módulo '{scraper_module_name}' não possui uma classe 'Scraper'.")
            raise ValueError(f"Classe 'Scraper' não encontrada no módulo '{scraper_module_name}'.")

class BaseScraper:
    """
    Classe base que todos os scrapers modulares devem herdar e implementar.
    """
    def executar(self, page, cnpj: str, client_folder: str) -> str:
        """
        Método principal de execução.
        :param page: Instância do Playwright Page
        :param cnpj: CNPJ limpo do cliente
        :param client_folder: Caminho da pasta do cliente para salvar o PDF
        :return: Caminho do arquivo PDF salvo
        """
        raise NotImplementedError("O método 'executar' deve ser implementado nas subclasses.")
    
    def salvar_arquivo(self, content: bytes, nome_arquivo: str, client_folder: str) -> str:
        """
        Salva o arquivo PDF na pasta do cliente, sobrescrevendo se existir.
        """
        from pathlib import Path
        path = Path(client_folder) / nome_arquivo
        with open(path, "wb") as f:
            f.write(content)
        return str(path)
