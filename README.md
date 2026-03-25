# Hub CND Politeto - Worker RPA

Responsável por emitir as certidões nos sites dos órgãos emissores, rodando localmente no cliente (distributed polling).

## Tecnologias
- Python 3.10+
- Playwright (Headless configurável)
- Pytesseract (OCR para Captcha simples) / 2Captcha

## Execução
O worker é inicializado no ambiente do cliente e faz polling a cada 1 segundo no banco central buscando jobs.
Limitação de 1 instância do browser por worker.