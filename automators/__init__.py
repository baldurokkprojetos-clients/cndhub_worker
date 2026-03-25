import logging
from .base import BaseAutomator
from .receita_federal import ReceitaFederalAutomator
from .prefeitura_goiania import PrefeituraGoianiaAutomator
from .caixa_fgts import CaixaFgtsAutomator
from .trabalhista_tst import TrabalhistaTstAutomator
from .sefaz_goias import SefazGoiasAutomator
from .projudi_goias import ProjudiGoiasAutomator

logger = logging.getLogger(__name__)

# Mapeamento do nome do módulo no banco (tipo_certidoes.automator_module) para a classe Python correspondente
AUTOMATORS_REGISTRY = {
    'receita_federal': ReceitaFederalAutomator,
    'prefeitura_goiania': PrefeituraGoianiaAutomator,
    'caixa_fgts': CaixaFgtsAutomator,
    'trabalhista_tst': TrabalhistaTstAutomator,
    'sefaz_goias': SefazGoiasAutomator,
    'projudi_goias': ProjudiGoiasAutomator,
}

def get_automator(module_name: str, cliente_id: str, tipo_certidao_id: str, cnpj: str, **kwargs) -> BaseAutomator:
    """
    Fábrica que instancia o robô adequado com base no module_name fornecido.
    """
    AutomatorClass = AUTOMATORS_REGISTRY.get(module_name)
    if not AutomatorClass:
        logger.error(f"Robô não encontrado para o módulo: {module_name}")
        raise ValueError(f"Robô '{module_name}' não suportado.")
        
    return AutomatorClass(
        cliente_id=cliente_id,
        tipo_certidao_id=tipo_certidao_id,
        cnpj=cnpj,
        **kwargs
    )
