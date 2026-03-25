import os
from google import genai
import logging
from PIL import Image

logger = logging.getLogger(__name__)

def solve_captcha_with_gemini(image: Image.Image) -> str:
    """
    Decodes a captcha image using Gemini 2.5 Flash Lite.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY não configurada no .env")
        return ""
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = "Extract the text from this captcha image. Return ONLY the extracted characters without any formatting, spaces, or extra words."
        
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=[image, prompt]
        )
        
        if response.text:
            text = response.text.strip().replace(" ", "")
            logger.info(f"Captcha resolvido via Gemini: {text}")
            return text
            
        return ""
    except Exception as e:
        logger.error(f"Erro ao resolver captcha com Gemini: {e}")
        return ""
