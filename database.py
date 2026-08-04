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
    # Features 1.2/1.4/2.1 del spec: perfil y panel admin
    nombre = Column(String, nullable=True)
    ranking_optin = Column(Boolean, default=False)
    fecha_primer_login = Column(DateTime, nullable=True)
    is_admin = Column(Boolean, default=False)
    admin_password_hash = Column(String, nullable=True)


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_banner = Column(String, index=True, nullable=False)
    mensaje = Column(String, nullable=False)
    curso = Column(String, nullable=True)
    componente = Column(String, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now, index=True)
    leida = Column(Boolean, default=False)


class Sugerencia(Base):
    __tablename__ = "sugerencias"

    id = Column(Integer, primary_key=True, index=True)
    usuario_banner = Column(String, index=True, nullable=False)
    texto = Column(Text, nullable=False)
    estado = Column(String, default="pendiente")
    fecha_creacion = Column(DateTime, default=datetime.now, index=True)


class CourseGradeAnon(Base):
    __tablename__ = "course_grades_anon"

    id = Column(Integer, primary_key=True, index=True)
    usuario_banner = Column(String, index=True, nullable=False)
    course_id = Column(String, index=True, nullable=False)
    course_name = Column(String, nullable=True)
    nota = Column(String, nullable=True)
    ciclo = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.now, index=True)


class DailyActivity(Base):
    __tablename__ = "daily_activity"

    id = Column(Integer, primary_key=True, index=True)
    usuario_banner = Column(String, index=True, nullable=False)
    fecha = Column(DateTime, nullable=False, index=True)


class RequestLog(Base):
    __tablename__ = "request_log"

    id = Column(Integer, primary_key=True, index=True)
    usuario_banner = Column(String, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.now, index=True)


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id = Column(Integer, primary_key=True)
    clave = Column(String, unique=True, nullable=False)
    valor = Column(Text, nullable=True)

Base.metadata.create_all(bind=engine)

def _migrate_missing_columns():
    """Agrega columnas nuevas a tablas SQLite ya existentes (ALTER TABLE)."""
    try:
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("user_settings")}
        nuevas_columnas = {
            "intervalo_chequeo_minutos": "ALTER TABLE user_settings ADD COLUMN intervalo_chequeo_minutos INTEGER DEFAULT 10",
            "ultima_revision": "ALTER TABLE user_settings ADD COLUMN ultima_revision DATETIME",
            "nombre": "ALTER TABLE user_settings ADD COLUMN nombre VARCHAR",
            "ranking_optin": "ALTER TABLE user_settings ADD COLUMN ranking_optin BOOLEAN DEFAULT 0",
            "fecha_primer_login": "ALTER TABLE user_settings ADD COLUMN fecha_primer_login DATETIME",
            "is_admin": "ALTER TABLE user_settings ADD COLUMN is_admin BOOLEAN DEFAULT 0",
            "admin_password_hash": "ALTER TABLE user_settings ADD COLUMN admin_password_hash VARCHAR",
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
