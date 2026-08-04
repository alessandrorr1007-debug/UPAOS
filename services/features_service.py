import re
import unicodedata
from datetime import date, datetime, timedelta
from bs4 import BeautifulSoup

import bcrypt
from sqlalchemy.orm import Session

from database import (
    CourseGradeAnon,
    DailyActivity,
    GlobalSetting,
    RequestLog,
    Sugerencia,
    UserSetting,
)

# ---------------------------------------------------------------------------
# Constantes del spec de funcionalidades
# ---------------------------------------------------------------------------
MIN_RANKING_USUARIOS = 5          # 1.2: mínimo de participantes para mostrar posición
SUGERENCIAS_POR_DIA = 3           # 1.1: límite anti-spam de sugerencias por día
SUGERENCIA_MIN_LEN = 10           # 1.1: longitud mínima del texto
SUGERENCIA_MAX_LEN = 500          # 1.1: longitud máxima del texto
TOTAL_SEMANAS_CICLO = 16          # 1.3: semanas regulares del ciclo
ADMIN_USUARIO = "000279330"       # 2.1: cuenta del panel de administración
ADMIN_PASSWORD_PLAIN = "Alessandro2002"  # 2.1: password independiente del portal (bcrypt)


def normalizar_course_id(codigo_materia, numero_curso) -> str:
    """
    course_id único = subjectCode + courseNumber (ej. 'HUMA' + '1185' -> 'HUMA-1185').
    Se normaliza: mayúsculas, sin tildes, separador único '-', sin espacios.
    """
    texto = f"{codigo_materia}-{numero_curso}" if numero_curso not in (None, "") else str(codigo_materia or "")
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8", "ignore")
    texto = re.sub(r"[^A-Za-z0-9]", "-", texto.upper())
    texto = re.sub(r"-+", "-", texto).strip("-")
    return texto


# ---------------------------------------------------------------------------
# 1.3 Semana académica (ciclo: 16 semanas regulares + sustitutorios + finales)
# ---------------------------------------------------------------------------
def semana_academica(db: Session) -> dict:
    reg = db.query(GlobalSetting).filter(GlobalSetting.clave == "ciclo_inicio_fecha").first()
    hoy = date.today()
    if not reg or not reg.valor:
        return {
            "configurada": False,
            "semana": None,
            "total_semanas": TOTAL_SEMANAS_CICLO,
            "etiqueta": None,
            "fuera_de_ciclo": None,
            "fecha_inicio": None,
            "dias_transcurridos": None,
        }

    try:
        if "T" in reg.valor:
            inicio = datetime.fromisoformat(reg.valor).date()
        else:
            inicio = datetime.strptime(reg.valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {
            "configurada": False,
            "semana": None,
            "total_semanas": TOTAL_SEMANAS_CICLO,
            "etiqueta": None,
            "fuera_de_ciclo": None,
            "fecha_inicio": reg.valor,
            "dias_transcurridos": None,
        }

    dias = (hoy - inicio).days
    semana = max(dias, 0) // 7 + 1 if dias >= 0 else 0

    if semana == 0:
        etiqueta, fuera = "El ciclo aún no inicia", True
    elif semana <= TOTAL_SEMANAS_CICLO:
        etiqueta, fuera = f"Semana {semana} de {TOTAL_SEMANAS_CICLO}", False
    elif semana == TOTAL_SEMANAS_CICLO + 1:
        etiqueta, fuera = "Semana 17 · Sustitutorios", False
    elif semana == TOTAL_SEMANAS_CICLO + 2:
        etiqueta, fuera = "Semana 18 · Exámenes Finales", False
    else:
        etiqueta, fuera = "Fuera de ciclo", True

    return {
        "configurada": True,
        "semana": semana,
        "total_semanas": TOTAL_SEMANAS_CICLO,
        "etiqueta": etiqueta,
        "fuera_de_ciclo": fuera,
        "fecha_inicio": inicio.isoformat(),
        "dias_transcurridos": max(dias, 0),
    }


def establecer_semana_inicio(db: Session, fecha_inicio: str) -> dict:
    reg = db.query(GlobalSetting).filter(GlobalSetting.clave == "ciclo_inicio_fecha").first()
    if reg is None:
        reg = GlobalSetting(clave="ciclo_inicio_fecha", valor=fecha_inicio)
        db.add(reg)
    else:
        reg.valor = fecha_inicio
    db.commit()
    return semana_academica(db)


# ---------------------------------------------------------------------------
# 1.1 Buzón de sugerencias (con límite diario anti-spam)
# ---------------------------------------------------------------------------
def registrar_sugerencia(db: Session, usuario: str, texto: str) -> dict:
    texto = (texto or "").strip()
    if len(texto) < SUGERENCIA_MIN_LEN:
        raise ValueError(f"La sugerencia debe tener al menos {SUGERENCIA_MIN_LEN} caracteres.")
    if len(texto) > SUGERENCIA_MAX_LEN:
        raise ValueError(f"La sugerencia no puede superar los {SUGERENCIA_MAX_LEN} caracteres.")

    inicio_hoy = datetime.combine(date.today(), datetime.min.time())
    enviadas_hoy = (
        db.query(Sugerencia)
        .filter(
            Sugerencia.usuario_banner == usuario,
            Sugerencia.fecha_creacion >= inicio_hoy,
        )
        .count()
    )
    if enviadas_hoy >= SUGERENCIAS_POR_DIA:
        raise ValueError(f"Límite de {SUGERENCIAS_POR_DIA} sugerencias por día alcanzado. Vuelve mañana.")

    sugerencia = Sugerencia(usuario_banner=usuario, texto=texto, estado="pendiente")
    db.add(sugerencia)
    db.commit()
    return {"sugerencia_id": sugerencia.id, "estado": sugerencia.estado}


def listar_mis_sugerencias(db: Session, usuario: str) -> list:
    filas = (
        db.query(Sugerencia)
        .filter(Sugerencia.usuario_banner == usuario)
        .order_by(Sugerencia.fecha_creacion.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "texto": s.texto,
            "estado": s.estado,
            "fecha_creacion": s.fecha_creacion.isoformat() if s.fecha_creacion else None,
        }
        for s in filas
    ]


def listar_todas_sugerencias(db: Session, solo_pendientes: bool = False) -> list:
    query = db.query(Sugerencia)
    if solo_pendientes:
        query = query.filter(Sugerencia.estado == "pendiente")
    filas = query.order_by(Sugerencia.fecha_creacion.desc()).all()
    return [
        {
            "id": s.id,
            "usuario": s.usuario_banner,
            "texto": s.texto,
            "estado": s.estado,
            "fecha_creacion": s.fecha_creacion.isoformat() if s.fecha_creacion else None,
        }
        for s in filas
    ]


def actualizar_estado_sugerencia(db: Session, sugerencia_id: int, estado: str) -> dict:
    if estado not in ("pendiente", "en_revision", "aprobada", "rechazada"):
        raise ValueError("Estado inválido. Use: pendiente, en_revision, aprobada o rechazada.")
    sugerencia = db.query(Sugerencia).filter(Sugerencia.id == sugerencia_id).first()
    if not sugerencia:
        raise ValueError("Sugerencia no encontrada.")
    sugerencia.estado = estado
    db.commit()
    return {"id": sugerencia.id, "estado": sugerencia.estado}


# ---------------------------------------------------------------------------
# 1.2 Ranking anónimo por curso (opt-in global, nunca expone notas)
# ---------------------------------------------------------------------------
def set_ranking_optin(db: Session, usuario: str, enabled: bool) -> dict:
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if user is None:
        raise ValueError("Usuario no registrado en ajustes.")
    user.ranking_optin = bool(enabled)
    db.commit()
    return {"ranking_optin": bool(user.ranking_optin)}


def registrar_cursos_ranking(db: Session, usuario: str, ciclo: str, cursos: list) -> int:
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if user is None or not user.ranking_optin:
        return 0

    insertados = 0
    for c in cursos:
        course_id = c.get("course_id")
        nota = c.get("nota")
        if not course_id or nota is None:
            continue
        fila = (
            db.query(CourseGradeAnon)
            .filter(
                CourseGradeAnon.usuario_banner == usuario,
                CourseGradeAnon.course_id == course_id,
                CourseGradeAnon.ciclo == ciclo,
            )
            .first()
        )
        if fila is None:
            db.add(CourseGradeAnon(
                usuario_banner=usuario,
                course_id=course_id,
                course_name=c.get("course_name"),
                nota=str(nota),
                ciclo=ciclo,
                timestamp=datetime.now(),
            ))
            insertados += 1
        else:
            fila.nota = str(nota)
            fila.course_name = c.get("course_name") or fila.course_name
            fila.timestamp = datetime.now()
    db.commit()
    return insertados


def registrar_snapshot_ranking(db: Session, usuario: str, ciclo: str, snapshot: list) -> int:
    cursos = [
        {"course_id": c.get("course_id"), "course_name": c.get("curso"), "nota": c.get("nota_actual")}
        for c in snapshot
        if isinstance(c, dict)
    ]
    return registrar_cursos_ranking(db, usuario, ciclo, cursos)


def obtener_ranking(db: Session, usuario: str, course_id: str, ciclo: str) -> dict:
    base = {
        "course_id": course_id,
        "ciclo": ciclo,
        "min_usuarios": MIN_RANKING_USUARIOS,
        "position": None,
        "total": 0,
        "percentil": None,
    }

    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if user is None or not user.ranking_optin:
        return {**base, "disponible": False, "motivo": "optin_inactivo"}

    filas = (
        db.query(CourseGradeAnon)
        .filter(
            CourseGradeAnon.course_id == course_id,
            CourseGradeAnon.ciclo == ciclo,
        )
        .all()
    )
    con_nota = [f for f in filas if f.nota is not None]

    if len(con_nota) < MIN_RANKING_USUARIOS:
        return {**base, "disponible": False, "motivo": "insuficientes", "total": len(con_nota)}

    mia = next((f for f in con_nota if f.usuario_banner == usuario), None)
    if mia is None:
        return {**base, "disponible": False, "motivo": "sin_datos", "total": len(con_nota)}

    try:
        mi_nota = float(mia.nota)
    except (TypeError, ValueError):
        return {**base, "disponible": False, "motivo": "sin_datos", "total": len(con_nota)}

    position = sum(1 for f in con_nota if _a_float(f.nota) is not None and _a_float(f.nota) > mi_nota) + 1
    total = len(con_nota)
    percentil = round(position * 100 / total)

    return {
        **base,
        "disponible": True,
        "motivo": None,
        "position": position,
        "total": total,
        "percentil": percentil,
    }


def _a_float(valor):
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 1.4 Nombre del estudiante (extracción limpia HTML Banner SSB / WSO2)
# ---------------------------------------------------------------------------
def extraer_nombre_estudiante(session) -> str | None:
    if session is None:
        return None
    try:
        url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            for sel in [".user-name", "#user-name", ".profile-name", ".student-name", "span.name"]:
                elem = soup.select_one(sel)
                if elem and elem.text.strip():
                    return elem.text.strip()
            match = re.search(r'["\']fullName["\']\s*:\s*["\']([^"\']+)["\']', res.text)
            if match:
                return match.group(1).strip()
    except Exception as e:
        print(f"[Features] Error en extracción de nombre: {e}")
    return None


def obtener_cuenta(db: Session, usuario: str) -> dict | None:
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if user is None:
        return None
    return {
        "usuario": user.usuario_campus,
        "nombre": user.nombre,
        "is_admin": bool(user.is_admin),
        "ranking_optin": bool(user.ranking_optin),
        "auto_check_enabled": bool(user.auto_check_enabled),
        "tiene_password_guardada": bool(user.password_encriptada),
        "fecha_primer_login": user.fecha_primer_login.isoformat() if user.fecha_primer_login else None,
    }


def listar_cuentas_registradas(db: Session) -> list:
    filas = db.query(UserSetting).all()
    return [
        {
            "usuario": u.usuario_campus,
            "nombre": u.nombre,
            "is_admin": bool(u.is_admin),
            "ranking_optin": bool(u.ranking_optin),
            "auto_check_enabled": bool(u.auto_check_enabled),
            "tiene_password_guardada": bool(u.password_encriptada),
            "fecha_primer_login": u.fecha_primer_login.isoformat() if u.fecha_primer_login else None,
            "ultima_revision": u.ultima_revision.isoformat() if u.ultima_revision else None,
        }
        for u in filas
    ]


# ---------------------------------------------------------------------------
# Métricas 2.2/2.3/2.4: actividad diaria (DAU) y pico máximo simultáneo
# ---------------------------------------------------------------------------
def registrar_actividad(db: Session, usuario: str) -> None:
    if not usuario:
        return
    hoy = datetime.combine(date.today(), datetime.min.time())
    fila = (
        db.query(DailyActivity)
        .filter(DailyActivity.usuario_banner == usuario, DailyActivity.fecha == hoy)
        .first()
    )
    if fila is None:
        db.add(DailyActivity(usuario_banner=usuario, fecha=hoy))
    db.add(RequestLog(usuario_banner=usuario, timestamp=datetime.now()))
    try:
        db.commit()
    except Exception:
        db.rollback()


def serie_dau(db: Session, dias: int = 30) -> list:
    desde = date.today() - timedelta(days=dias - 1)
    filas = (
        db.query(DailyActivity)
        .filter(DailyActivity.fecha >= desde)
        .all()
    )
    agrupado: dict[date, int] = {}
    for f in filas:
        dia = f.fecha.date() if isinstance(f.fecha, datetime) else f.fecha
        agrupado[dia] = agrupado.get(dia, 0) + 1
    return [
        {"fecha": (desde + timedelta(days=offset)).isoformat(), "usuarios": agrupado.get(desde + timedelta(days=offset), 0)}
        for offset in range(dias)
    ]


def cuentas_activas_hoy(db: Session) -> int:
    hoy = datetime.combine(date.today(), datetime.min.time())
    return (
        db.query(DailyActivity)
        .filter(DailyActivity.fecha == hoy)
        .count()
    )


def _pico_por_minuto(db: Session, desde: datetime | None = None) -> dict | None:
    query = db.query(RequestLog)
    if desde is not None:
        query = query.filter(RequestLog.timestamp >= desde)
    filas = query.all()
    if not filas:
        return None
    agrupado: dict[str, int] = {}
    for f in filas:
        ts = f.timestamp
        if ts is None:
            continue
        if isinstance(ts, datetime):
            clave = ts.strftime("%Y-%m-%d %H:%M")
        else:
            clave = str(ts)
        agrupado[clave] = agrupado.get(clave, 0) + 1
    clave_max = max(agrupado, key=agrupado.get)
    return {"fecha_hora": clave_max, "usuarios_simultaneos": agrupado[clave_max]}


def pico_hoy(db: Session) -> dict | None:
    return _pico_por_minuto(db, desde=datetime.combine(date.today(), datetime.min.time()))


def pico_historico(db: Session) -> dict | None:
    return _pico_por_minuto(db)


# ---------------------------------------------------------------------------
# 2.1 Panel admin: autenticación bcrypt y seed de la cuenta admin
# ---------------------------------------------------------------------------
def hash_password_admin(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password_admin(user: UserSetting, password: str) -> bool:
    if user is None or not user.admin_password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), user.admin_password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def asegurar_admin(db: Session) -> None:
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == ADMIN_USUARIO).first()
    if user is None:
        user = UserSetting(
            usuario_campus=ADMIN_USUARIO,
            password_encriptada="",
            auto_check_enabled=False,
            is_admin=True,
            admin_password_hash=hash_password_admin(ADMIN_PASSWORD_PLAIN),
        )
        db.add(user)
        print(f"[Features] Cuenta admin creada: {ADMIN_USUARIO}")
    else:
        user.is_admin = True
        user.admin_password_hash = hash_password_admin(ADMIN_PASSWORD_PLAIN)
        print(f"[Features] Cuenta admin {ADMIN_USUARIO} actualizada con privilegios y contraseña.")
    db.commit()
