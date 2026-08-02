import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "UPAO Campus Virtual API"
    CAMPUS_URL: str = os.getenv("CAMPUS_URL", "https://campusvirtual.upao.edu.pe/login.aspx")
    CAPTCHA_URL: str = os.getenv("CAPTCHA_URL", "https://campusvirtual.upao.edu.pe/captcha.ashx")
    NOTAS_URL: str = os.getenv("NOTAS_URL", "https://campusvirtual.upao.edu.pe/Notas.aspx")
    
    FERNET_KEY: str = os.getenv("FERNET_KEY", os.getenv("SECRET_KEY", "b3ZlcnJpZGVfdGhpc193aXRoX2FfcmVhbF9mZXJuZXRfa2V5X2luX3Byb2Q="))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app_data.db")
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "/usr/bin/tesseract")

settings = Settings()
