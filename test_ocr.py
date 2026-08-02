import sys
import os
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter

def test_ocr_file(image_path: str):
    if not os.path.exists(image_path):
        print(f"[Error] Archivo no encontrado: {image_path}")
        return

    print(f"\n--- Probando OCR en imagen: {image_path} ---")
    image = Image.open(image_path)
    print(f"Tamaño original: {image.width}x{image.height}, Modo: {image.mode}")

    # Escalar imagen 2x para mejorar nitidez de Tesseract
    scaled = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    gray = scaled.convert('L')
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(2.0)

    custom_config = r'-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --psm 6'

    # Probar diferentes umbrales (thresholds)
    thresholds = [100, 120, 140, 160, 180]
    for th in thresholds:
        binary = enhanced.point(lambda p: 255 if p > th else 0)
        raw_text = pytesseract.image_to_string(binary, config=custom_config)
        cleaned = raw_text.strip().upper().replace(" ", "")
        valid = (len(cleaned) == 6 and cleaned.isalnum())
        print(f"[Umbral {th}] Texto leído: '{cleaned}' (Longitud: {len(cleaned)}, Válido 6-chars: {valid})")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_ocr.py <ruta_de_la_imagen_captcha>")
    else:
        test_ocr_file(sys.argv[1])
