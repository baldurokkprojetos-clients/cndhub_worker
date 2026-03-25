from abc import ABC, abstractmethod
import logging
from typing import Optional
from pathlib import Path
from core.config import settings

logger = logging.getLogger(__name__)

class BaseAutomator:
    """
    Classe base para todos os robôs.
    """
    
    def __init__(self, cliente_id: str, tipo_certidao_id: str, cnpj: str, **kwargs):
        self.cliente_id = cliente_id
        self.tipo_certidao_id = tipo_certidao_id
        self.cnpj = cnpj
        self.kwargs = kwargs
        
    def get_download_path(self) -> str:
        """Retorna o caminho onde os downloads devem ser salvos para este cliente"""
        base_dir = Path(settings.BASE_CERTIDOES_PATH)
        
        # Regra de negócio: a pasta deve ter como nome apenas os números do CNPJ.
        cnpj_limpo = ''.join(filter(str.isdigit, self.cnpj))
        client_dir = base_dir / cnpj_limpo
        client_dir.mkdir(parents=True, exist_ok=True)
        return str(client_dir)
        
    def execute(self) -> dict:
        """
        Método principal que deve ser implementado pelos robôs específicos.
        Deve retornar um dicionário com:
        - status: 'completed' ou 'error'
        - caminho_arquivo: path para o PDF baixado (se sucesso)
        - mensagem_erro: descrição do erro (se falha)
        """
        raise NotImplementedError("Os robôs devem implementar o método execute()")
        
    def cleanup_driver(self, driver):
        """Método utilitário para garantir o encerramento completo do ChromeDriver."""
        if not driver:
            return
            
        browser_pid = getattr(driver, 'browser_pid', None)
        
        try:
            driver.quit()
        except Exception as e:
            logger.warning(f"Erro ao executar driver.quit(): {e}")
            
        # Garante que o processo e subprocessos sejam mortos
        if browser_pid:
            try:
                import psutil
                parent = psutil.Process(browser_pid)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except:
                        pass
                try:
                    parent.kill()
                except:
                    pass
                logger.info(f"Processo do navegador PID {browser_pid} encerrado forçadamente para liberar memória.")
            except Exception as e:
                logger.debug(f"Processo PID {browser_pid} não encontrado ou já encerrado: {e}")
