import io
import pytesseract
from PIL import Image, ImageEnhance
from config import settings

if settings.TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

def process_captcha_ocr(image_bytes: bytes) -> str | None:
    """
    Preprocesa la imagen del captcha y extrae exactamente 6 caracteres alfanuméricos en mayúscula usando pytesseract.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        gray = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)
        
        threshold = 140
        binary = enhanced.point(lambda p: 255 if p > threshold else 0)
        
        custom_config = r'-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --psm 6'
        text = pytesseract.image_to_string(binary, config=custom_config)
        cleaned_text = text.strip().upper().replace(" ", "")
        
        if len(cleaned_text) == 6 and cleaned_text.isalnum():
            return cleaned_text
            
        binary_alt = enhanced.point(lambda p: 255 if p > 120 else 0)
        text_alt = pytesseract.image_to_string(binary_alt, config=custom_config)
        cleaned_alt = text_alt.strip().upper().replace(" ", "")
        
        if len(cleaned_alt) == 6 and cleaned_alt.isalnum():
            return cleaned_alt

        return None
    except Exception as e:
        print(f"[OCR Error] Failed to process captcha: {e}")
        return None
