import json
from cryptography.fernet import Fernet
from sqlalchemy import Boolean, Column, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config import settings

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

try:
    cipher_suite = Fernet(settings.FERNET_KEY.encode())
except Exception:
    key = Fernet.generate_key()
    cipher_suite = Fernet(key)

class UserSetting(Base):
    __tablename__ = "user_settings"

    usuario_campus = Column(String, primary_key=True, index=True)
    password_encriptada = Column(Text, nullable=False)
    auto_check_enabled = Column(Boolean, default=False)
    ultimo_snapshot_notas = Column(Text, nullable=True)
    fcm_token = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

def encrypt_password(plain_password: str) -> str:
    return cipher_suite.encrypt(plain_password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    return cipher_suite.decrypt(encrypted_password.encode()).decode()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
