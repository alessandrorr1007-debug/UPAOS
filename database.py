import json
from datetime import datetime
from cryptography.fernet import Fernet
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine, inspect
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
    intervalo_chequeo_minutos = Column(Integer, default=10)
    ultimo_snapshot_notas = Column(Text, nullable=True)
    ultima_revision = Column(DateTime, nullable=True)
    fcm_token = Column(String, nullable=True)


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_banner = Column(String, index=True, nullable=False)
    mensaje = Column(String, nullable=False)
    curso = Column(String, nullable=True)
    componente = Column(String, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now, index=True)
    leida = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

def _migrate_missing_columns():
    """Agrega columnas nuevas a tablas SQLite ya existentes (ALTER TABLE)."""
    try:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("user_settings")}
        nuevas_columnas = {
            "intervalo_chequeo_minutos": "ALTER TABLE user_settings ADD COLUMN intervalo_chequeo_minutos INTEGER DEFAULT 10",
            "ultima_revision": "ALTER TABLE user_settings ADD COLUMN ultima_revision DATETIME",
        }
        with engine.begin() as conn:
            for name, ddl in nuevas_columnas.items():
                if name not in columns:
                    conn.exec_driver_sql(ddl)
                    print(f"[DB] Columna añadida: {name}")
    except Exception as e:
        print(f"[DB Warning] No se pudieron migrar columnas: {e}")

_migrate_missing_columns()

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

def guardar_notificaciones(db, usuario_banner: str, cambios: list):
    """Persiste filas de notificación (leida=False) para cada cambio detectado."""
    for c in cambios:
        db.add(Notificacion(
            usuario_banner=usuario_banner,
            mensaje=c.get("mensaje", ""),
            curso=c.get("curso"),
            componente=c.get("componente"),
            fecha_creacion=datetime.now(),
            leida=False,
        ))
    db.commit()
