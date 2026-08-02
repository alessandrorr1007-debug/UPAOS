import json
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import settings
from database import get_db, UserSetting, Notificacion, encrypt_password, decrypt_password
from services.scraper_service import scraper_service, ACTIVE_SESSIONS
from services.banner_sso_service import banner_sso_service
from services.notification_service import notification_service
from services import auto_check_service


def _tick_auto_check():
    try:
        auto_check_service.run_auto_check()
    except Exception as e:
        print(f"[Scheduler] Error en tick auto_check: {e}")
        print(traceback.format_exc())


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone="America/Lima")
    scheduler.add_job(
        _tick_auto_check,
        trigger=IntervalTrigger(minutes=5),
        id="auto_check",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    print("[Scheduler] Job auto_check iniciado (cada 5 min, respeta el intervalo por usuario).")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

@app.middleware("http")
def log_requests(request: Request, call_next):
    print(f"\n==================== [PETICIÓN ENTRANTE: {request.method} {request.url}] ====================")
    print(f"Headers: {dict(request.headers)}")
    try:
        response = call_next(request)
        return response
    except Exception as e:
        print(f"[ERROR EXCEPCIÓN BACKEND]: {e}")
        print(traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": f"Error interno en backend: {str(e)}", "traceback": traceback.format_exc()}
        )

class LoginRequest(BaseModel):
    usuario: str = Field(..., description="ID/Usuario de 9 dígitos del campus")
    password: str = Field(..., description="Contraseña del usuario")

class ManualCaptchaRequest(BaseModel):
    usuario: str
    password: str
    codigo_manual: str

class NotasBuscarRequest(BaseModel):
    periodo: str = Field(default="202610")
    carrera: str = Field(default="UG")

class NotasDetalleRequest(BaseModel):
    # Nombres reales del JSON de Banner /courses. Se aceptan también los alias
    # "periodo"/"crn" que envía la app Android actual (populate_by_name=True).
    model_config = ConfigDict(populate_by_name=True)
    termCode: str = Field(..., description="termCode del periodo, ej. 202610", alias="periodo")
    courseReferenceNumber: str = Field(..., description="courseReferenceNumber del curso (viene en el JSON de /courses)", alias="crn")

class AutoCheckSetting(BaseModel):
    enabled: bool

class IntervaloSetting(BaseModel):
    minutos: int = Field(..., description="Intervalo de chequeo en minutos: 5, 10, 15 o 30")

class DeviceTokenRequest(BaseModel):
    fcm_token: str

@app.get("/")
def read_root():
    return {
        "message": "API de consulta UPAO Campus Virtual / Banner SSB activa",
        "firebase_status": "Inicializado" if notification_service.initialized else "No configurado",
        "status": "ok"
    }

@app.get("/healthz")
def healthz():
    """Endpoint liviano para cron externo (evita que Render duerma el servicio)."""
    return {"status": "ok", "service": "upaos-api", "time": datetime.utcnow().isoformat()}

@app.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    print(f"[Login Request] Usuario: {req.usuario}")
    result = scraper_service.login(req.usuario, req.password)
    if result.get("success"):
        existing_user = db.query(UserSetting).filter(UserSetting.usuario_campus == req.usuario).first()
        if not existing_user:
            user_entry = UserSetting(
                usuario_campus=req.usuario,
                password_encriptada=encrypt_password(req.password),
                auto_check_enabled=False
            )
            db.add(user_entry)
        else:
            existing_user.password_encriptada = encrypt_password(req.password)
        db.commit()
    print(f"[Login Response]: {result}")
    return result

@app.post("/login/confirmar-captcha")
def login_confirmar_captcha(req: ManualCaptchaRequest, db: Session = Depends(get_db)):
    result = scraper_service.login(req.usuario, req.password, manual_captcha=req.codigo_manual)
    if result.get("success"):
        existing_user = db.query(UserSetting).filter(UserSetting.usuario_campus == req.usuario).first()
        if not existing_user:
            user_entry = UserSetting(
                usuario_campus=req.usuario,
                password_encriptada=encrypt_password(req.password),
                auto_check_enabled=False
            )
            db.add(user_entry)
        else:
            existing_user.password_encriptada = encrypt_password(req.password)
        db.commit()
    return result

@app.get("/notas/periodos")
def get_periodos(authorization: str | None = Header(None, alias="Authorization")):
    print(f"[GET /notas/periodos] Authorization Header recibido: {authorization}")
    session = None
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        session = ACTIVE_SESSIONS.get(token)

    if session:
        banner_res = banner_sso_service.get_periodos(session)
        if banner_res.get("success"):
            raw_periodos = banner_res.get("periodos", [])
            periodos_str_list = [p.get("code") for p in raw_periodos if p.get("code")]
            return {
                # Regla compartida: periodo regular (termina en 10/20, excluye 90)
                # con el código numérico más alto (el más reciente).
                "periodo_actual": banner_sso_service.periodo_actual(raw_periodos),
                "periodos": periodos_str_list,
                "detalles_periodos": raw_periodos
            }

    # Sin sesión activa de Banner no se inventan periodos: lista vacía para que el
    # cliente use su propio valor por defecto. La lista siempre viene del GET /term real.
    return {
        "periodo_actual": None,
        "periodos": [],
        "detalles_periodos": [],
        "message": "Sin sesión activa de Banner para consultar periodos en vivo"
    }

@app.get("/notas/carreras")
def get_carreras(term: str = "202610", authorization: str | None = Header(None, alias="Authorization")):
    print(f"[GET /notas/carreras] Term: {term}, Authorization: {authorization}")
    session = None
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
        session = ACTIVE_SESSIONS.get(token)

    if session:
        banner_res = banner_sso_service.get_niveles(session, term)
        if banner_res.get("success"):
            raw_niveles = banner_res.get("niveles", [])
            carreras_str_list = [n.get("code") for n in raw_niveles if n.get("code")]
            return {
                "carreras": carreras_str_list if carreras_str_list else ["UG"],
                "detalles_carreras": raw_niveles
            }

    return {"carreras": ["UG"]}

@app.post("/notas/buscar")
def buscar_notas(req: NotasBuscarRequest, authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    print(f"[POST /notas/buscar] Token: {token[:15]}..., Periodo: {req.periodo}, Nivel: {req.carrera}")
    
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        print(f"[ERROR /notas/buscar] Sesión no encontrada en ACTIVE_SESSIONS.")
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido.")

    result = banner_sso_service.get_courses_con_notas(session, req.periodo, req.carrera)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Error al consultar cursos en Banner"))

    # Momento en que Banner respondió (la app lo muestra como "Actualizado hace X").
    ultima_actualizacion = datetime.now().isoformat()
    raw_cursos = result.get("cursos", [])
    normalized_cursos = []

    # Extraer la lista real de cursos contenida en 'data' si viniera anidada
    if isinstance(raw_cursos, dict):
        raw_cursos = raw_cursos.get("data", [])

    if isinstance(raw_cursos, list):
        for item in raw_cursos:
            if isinstance(item, dict):
                course_title = item.get("courseTitle") or item.get("subjectDescription") or item.get("courseNumber") or item.get("nombre") or "Curso"
                # nota_actual viene enriquecida desde los componentes reales
                # (get_courses_con_notas): promedio ponderado progresivo o None.
                nota_actual = item.get("nota_actual")
                crn = item.get("courseReferenceNumber") or item.get("crn") or item.get("id")

                normalized_cursos.append({
                    "nombre": str(course_title),
                    "nota_actual": nota_actual,
                    "crn": str(crn) if crn else "",
                    "ep1": {"nota": None, "detalles": []},
                    "ep2": {"nota": None, "detalles": []},
                    "raw_banner": item
                })

    promedio_general, promedio_basado_en = banner_sso_service._calcular_promedio_general(normalized_cursos)

    response_data = {
        "periodo": req.periodo,
        "carrera": req.carrera,
        "ultima_actualizacion": ultima_actualizacion,
        "cursos": normalized_cursos,
        "totalCount": len(normalized_cursos),
        "promedio_general": promedio_general,
        "promedio_basado_en": promedio_basado_en
    }
    print(f"[SUCCESS /notas/buscar] Retornando {len(normalized_cursos)} cursos + promedio_general={promedio_general} (base: {promedio_basado_en}).")
    return response_data

@app.post("/notas/detalle")
def buscar_detalle_curso(req: NotasDetalleRequest, authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido")

    print(f"[POST /notas/detalle] termCode={req.termCode}, courseReferenceNumber={req.courseReferenceNumber}")
    result = banner_sso_service.get_course_grade_detail(session, req.termCode, req.courseReferenceNumber)
    return result

@app.get("/asistencia")
def get_asistencia(authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    print(f"[GET /asistencia] Token: {token[:15]}...")
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido")

    result = banner_sso_service.get_attendance(session)
    print(f"[SUCCESS /asistencia] Total registros: {result.get('totalCount')}")
    return result

@app.patch("/settings/auto-check")
def update_auto_check(req: AutoCheckSetting, usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no registrado en ajustes")
    user.auto_check_enabled = req.enabled
    db.commit()
    return {"message": "Configuración actualizada correctamente", "auto_check_enabled": req.enabled}

@app.patch("/settings/intervalo")
def update_intervalo(req: IntervaloSetting, usuario: str, db: Session = Depends(get_db)):
    if req.minutos not in (5, 10, 15, 30):
        raise HTTPException(status_code=422, detail="El intervalo debe ser uno de: 5, 10, 15, 30 minutos")
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no registrado en ajustes")
    user.intervalo_chequeo_minutos = req.minutos
    db.commit()
    return {"message": "Intervalo actualizado correctamente", "intervalo_chequeo_minutos": req.minutos}

@app.get("/settings")
def get_settings(usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no registrado en ajustes")
    return {
        "auto_check_enabled": bool(user.auto_check_enabled),
        "intervalo_chequeo_minutos": user.intervalo_chequeo_minutos or 10,
        "tiene_token_fcm": bool(user.fcm_token),
        "ultima_revision": user.ultima_revision.isoformat() if user.ultima_revision else None,
    }

@app.post("/device-token")
def update_device_token(req: DeviceTokenRequest, usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.fcm_token = req.fcm_token
    db.commit()
    
    if req.fcm_token and notification_service.initialized:
        notification_service.send_push_notification(
            token=req.fcm_token,
            title="UPAO Notas Conectado",
            body="Notificaciones activadas para actualizaciones de notas."
        )

    return {"message": "Token de dispositivo FCM actualizado correctamente", "firebase": notification_service.initialized}

@app.post("/notas/actualizar-ahora")
def actualizar_ahora(usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    cambios, snapshot = auto_check_service.revisar_usuario(user)
    if snapshot is None:
        return {"success": False, "message": "No se pudo obtener una sesión válida de Banner ni el periodo actual."}

    user.ultimo_snapshot_notas = json.dumps(snapshot)
    user.ultima_revision = datetime.now()
    db.commit()

    if cambios:
        auto_check_service.notificar_cambios(db, user, cambios)

    return {
        "success": True,
        "periodo": "automático",
        "cambios": [c["mensaje"] for c in cambios],
        "total_cambios": len(cambios),
    }

@app.get("/notificaciones")
def get_notificaciones(usuario: str, db: Session = Depends(get_db)):
    """Lista de notificaciones (recientes primero) + conteo de no leídas."""
    filas = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_banner == usuario)
        .order_by(Notificacion.fecha_creacion.desc())
        .all()
    )
    no_leidas = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_banner == usuario, Notificacion.leida.is_(False))
        .count()
    )
    return {
        "no_leidas": no_leidas,
        "total": len(filas),
        "notificaciones": [
            {
                "id": n.id,
                "mensaje": n.mensaje,
                "curso": n.curso,
                "componente": n.componente,
                "fecha_creacion": n.fecha_creacion.isoformat() if n.fecha_creacion else None,
                "leida": bool(n.leida),
            }
            for n in filas
        ],
    }

@app.patch("/notificaciones/marcar-leidas")
def marcar_notificaciones_leidas(usuario: str, db: Session = Depends(get_db)):
    """Marca todas las notificaciones del usuario como leídas."""
    result = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_banner == usuario, Notificacion.leida.is_(False))
        .update({"leida": True}, synchronize_session=False)
    )
    db.commit()
    return {"message": "Notificaciones marcadas como leídas", "marcadas": result}

@app.patch("/notificaciones/{notificacion_id}/marcar-leida")
def marcar_notificacion_leida(notificacion_id: int, usuario: str, db: Session = Depends(get_db)):
    """Marca una notificación específica como leída."""
    notif = (
        db.query(Notificacion)
        .filter(Notificacion.id == notificacion_id, Notificacion.usuario_banner == usuario)
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.leida = True
    db.commit()
    return {"message": "Notificación marcada como leída", "id": notif.id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
