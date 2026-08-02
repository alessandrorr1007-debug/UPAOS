import io
import os
import pytesseract
from PIL import Image, ImageEnhance
from config import settings

if settings.TESSERACT_CMD and os.path.exists(settings.TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

def process_captcha_ocr(image_bytes: bytes) -> str | None:
    """
    Preprocesa la imagen del captcha (redimensionamiento 2x, contraste y umbralización multinivel)
    e intenta extraer exactamente 6 caracteres alfanuméricos en mayúscula usando pytesseract.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        print(f"[OCR Log] Tamaño original del captcha: {image.width}x{image.height}, modo: {image.mode}")

        # 1. Redimensionar 2x (LANCZOS) para ampliar resolución y legibilidad de Tesseract
        scaled = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
        
        # 2. Escala de grises y aumento de contraste
        gray = scaled.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)
        
        custom_config = r'-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --psm 6'
        
        # 3. Probar múltiples niveles de binarización (Threshold)
        thresholds = [140, 120, 160, 100]
        
        for th in thresholds:
            binary = enhanced.point(lambda p: 255 if p > th else 0)
            raw_text = pytesseract.image_to_string(binary, config=custom_config)
            cleaned_text = raw_text.strip().upper().replace(" ", "").replace("\n", "")
            
            print(f"[OCR Log] Umbral {th} -> Leído: '{cleaned_text}' (Longitud: {len(cleaned_text)})")
            
            if len(cleaned_text) == 6 and cleaned_text.isalnum():
                print(f"[OCR Exitoso] Código de 6 caracteres reconocido: {cleaned_text}")
                return cleaned_text

        print("[OCR Fallido] Ningún umbral produjo exactamente 6 caracteres válidos. Activando fallback manual.")
        return None
    except Exception as e:
        print(f"[OCR Error] Excepción al procesar captcha: {e}")
        return None
