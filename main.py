import json
import os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from config import settings
from database import get_db, UserSetting, encrypt_password, decrypt_password
from services.scraper_service import scraper_service, ACTIVE_SESSIONS
from services.banner_sso_service import banner_sso_service

app = FastAPI(title=settings.APP_NAME)

class LoginRequest(BaseModel):
    usuario: str = Field(..., description="ID/Usuario de 9 dígitos del campus")
    password: str = Field(..., description="Contraseña del usuario")

class ManualCaptchaRequest(BaseModel):
    usuario: str
    password: str
    codigo_manual: str

class NotasBuscarRequest(BaseModel):
    periodo: str = Field(default="202690")
    carrera: str = Field(default="UB")

class AutoCheckSetting(BaseModel):
    enabled: bool

class DeviceTokenRequest(BaseModel):
    fcm_token: str

@app.get("/")
def read_root():
    return {"message": "API de consulta UPAO Campus Virtual / Banner SSB activa", "status": "ok"}

@app.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
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
def get_periodos(authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido")
    
    banner_res = banner_sso_service.get_periodos(session)
    if banner_res.get("success"):
        return banner_res
        
    # Fallback si no hay sesión Banner activa
    now = datetime.now()
    year = now.year
    semestre = "I" if now.month < 8 else "II"
    return {
        "periodo_actual": f"{year}-{semestre}",
        "periodos": [{"code": f"{year}90", "description": f"{year}-I"}, {"code": f"{year}10", "description": f"{year-1}-II"}]
    }

@app.get("/notas/carreras")
def get_carreras(term: str = "202690", authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido")
    
    banner_res = banner_sso_service.get_niveles(session, term)
    if banner_res.get("success"):
        return banner_res

    return {"carreras": [{"code": "UB", "description": "PREGRADO"}]}

@app.post("/notas/buscar")
def buscar_notas(req: NotasBuscarRequest, authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    session = ACTIVE_SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Sesión expirada o token inválido")

    result = banner_sso_service.get_courses(session, req.periodo, req.carrera)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Error al obtener cursos"))
    return result

@app.patch("/settings/auto-check")
def update_auto_check(req: AutoCheckSetting, usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no registrado en ajustes")
    user.auto_check_enabled = req.enabled
    db.commit()
    return {"message": "Configuración actualizada correctamente", "auto_check_enabled": req.enabled}

@app.post("/device-token")
def update_device_token(req: DeviceTokenRequest, usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.fcm_token = req.fcm_token
    db.commit()
    return {"message": "Token de dispositivo actualizado correctamente"}

@app.post("/notas/actualizar-ahora")
def actualizar_ahora(usuario: str, db: Session = Depends(get_db)):
    user = db.query(UserSetting).filter(UserSetting.usuario_campus == usuario).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    pass_decrypted = decrypt_password(user.password_encriptada)
    login_res = scraper_service.login(user.usuario_campus, pass_decrypted)
    
    if not login_res.get("success"):
        return {"success": False, "message": "No se pudo actualizar. " + login_res.get("message", "")}
        
    token = login_res.get("token")
    session = ACTIVE_SESSIONS.get(token)
    if session:
        notas = banner_sso_service.get_courses(session, "202690", "UB")
        user.ultimo_snapshot_notas = json.dumps(notas)
        db.commit()
        return {"success": True, "notas": notas}
    
    return {"success": False, "message": "No se obtuvo sesión activa"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
