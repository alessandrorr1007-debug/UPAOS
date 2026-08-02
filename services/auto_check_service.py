import json
import traceback
from datetime import datetime

from database import SessionLocal, UserSetting, decrypt_password
from services.banner_sso_service import banner_sso_service
from services.notification_service import notification_service
from services.scraper_service import scraper_service


def _fmt_nota(v):
    """Formatea la nota para el mensaje: 15.0 -> '15', 14.5 -> '14.5'."""
    if v is None:
        return None
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
        return str(f)
    except (TypeError, ValueError):
        return str(v)


def _construir_snapshot(session, term: str) -> list:
    """
    Obtiene los cursos del periodo actual y, para cada uno, consulta
    get_course_grade_detail() para extraer TODOS los componentes (EP1, Parcial,
    EP2, Final + subcomponentes) con su puntaje. Devuelve una estructura JSON
    serializable que se guarda como ultimo_snapshot_notas.
    """
    res = banner_sso_service.get_courses(session, term, "UG")
    raw = res.get("cursos", [])
    if isinstance(raw, dict):
        raw = raw.get("data", [])

    snapshot = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        crn = item.get("courseReferenceNumber") or item.get("crn") or item.get("id")
        nombre = (
            item.get("courseTitle")
            or item.get("subjectDescription")
            or item.get("courseNumber")
            or "Curso"
        )
        if not crn:
            continue

        detail = banner_sso_service.get_course_grade_detail(session, term, str(crn))
        componentes = {}
        for c in detail.get("detalles", []):
            if not isinstance(c, dict):
                continue
            cname = c.get("nombre") or "Componente"
            sub = {}
            for s in c.get("subcomponentes", []):
                sub[s.get("nombre", "Sub")] = _fmt_nota(s.get("puntaje_obtenido"))
            componentes[cname] = {
                "nota": _fmt_nota(c.get("puntaje_obtenido")),
                "sub": sub,
            }
        snapshot.append({"crn": str(crn), "curso": str(nombre), "componentes": componentes})

    print(f"[AutoCheck] Snapshot construido para {term}: {len(snapshot)} cursos.")
    return snapshot


def _comparar_snapshots(prev, nuevo) -> list:
    """
    Compara el snapshot anterior con el nuevo. Devuelve una lista de cambios
    legibles, p.ej. "Nueva nota en AGILE DEVELOPMENT: Evaluación de Proceso 2 = 15".
    La primera pasada (sin snapshot previo) no genera notificaciones.
    """
    if not prev:
        return []
    prev_por_crn = {c.get("crn"): c for c in prev}
    cambios = []
    for curso in nuevo:
        viejo = prev_por_crn.get(curso.get("crn"))
        for cname, data in curso.get("componentes", {}).items():
            nueva = data.get("nota")
            vieja = None
            if viejo:
                vieja = viejo.get("componentes", {}).get(cname, {}).get("nota")
            if nueva == vieja:
                continue
            if nueva is not None and vieja is None:
                cambios.append(f"Nueva nota en {curso.get('curso')}: {cname} = {nueva}")
            elif nueva is not None:
                cambios.append(f"Nota actualizada en {curso.get('curso')}: {cname} = {nueva} (antes {vieja})")
            else:
                cambios.append(f"Sin nota en {curso.get('curso')}: {cname}")
    return cambios


def revisar_usuario(user) -> tuple[list, list | None]:
    """
    Revisa las notas de un usuario:
      - Reutiliza la sesión de Banner cacheada (login completo solo si expiró).
      - Detecta el periodo actual (regla 10/20 excluyendo 90).
      - Construye el snapshot nuevo y lo compara con el guardado.
    Devuelve (cambios, nuevo_snapshot). nuevo_snapshot es None si no se pudo revisar.
    """
    try:
        pass_decrypted = decrypt_password(user.password_encriptada)
    except Exception as e:
        print(f"[AutoCheck] No se pudo descifrar la contraseña de {user.usuario_campus}: {e}")
        return [], None

    session, _ = scraper_service.obtener_sesion_valida(user.usuario_campus, pass_decrypted)
    if session is None:
        print(f"[AutoCheck] Sin sesión válida para {user.usuario_campus}.")
        return [], None

    periodos = banner_sso_service.get_periodos(session)
    term = banner_sso_service.periodo_actual(periodos.get("periodos", []))
    if not term:
        print(f"[AutoCheck] No se detectó periodo regular para {user.usuario_campus}.")
        return [], None

    snapshot = _construir_snapshot(session, term)

    prev = None
    if user.ultimo_snapshot_notas:
        try:
            prev = json.loads(user.ultimo_snapshot_notas)
        except (TypeError, ValueError):
            prev = None

    cambios = _comparar_snapshots(prev, snapshot)
    return cambios, snapshot


def run_auto_check():
    """
    Job del scheduler: recorre los usuarios con auto_check_enabled y revisa solo
    a los que ya les toca según su intervalo_chequeo_minutos.
    """
    db = SessionLocal()
    try:
        users = db.query(UserSetting).filter(UserSetting.auto_check_enabled.is_(True)).all()
        now = datetime.now()
        print(f"[AutoCheck] Pasada iniciada. Usuarios con auto-check: {len(users)}")

        for user in users:
            intervalo = user.intervalo_chequeo_minutos or 10
            if user.ultima_revision is not None:
                transcurrido = (now - user.ultima_revision).total_seconds() / 60.0
                if transcurrido < intervalo:
                    continue

            try:
                cambios, snapshot = revisar_usuario(user)
                if snapshot is None:
                    continue

                user.ultimo_snapshot_notas = json.dumps(snapshot)
                user.ultima_revision = datetime.now()
                db.commit()

                if cambios:
                    body = " · ".join(cambios[:5])
                    if len(cambios) > 5:
                        body += f" (+{len(cambios) - 5} más)"
                    print(f"[AutoCheck] Cambios para {user.usuario_campus}: {cambios}")
                    if user.fcm_token and notification_service.initialized:
                        notification_service.send_push_notification(
                            token=user.fcm_token,
                            title="Nueva nota en UPAO",
                            body=body,
                        )
                else:
                    print(f"[AutoCheck] Sin cambios para {user.usuario_campus}.")
            except Exception as e:
                print(f"[AutoCheck] Error procesando {user.usuario_campus}: {e}")
                print(traceback.format_exc())
                db.rollback()
    finally:
        db.close()
