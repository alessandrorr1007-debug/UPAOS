import json
import os
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from config import settings
from database import get_db, UserSetting, encrypt_password, decrypt_password
from services.scraper_service import scraper_service

app = FastAPI(title=settings.APP_NAME)

class LoginRequest(BaseModel):
    usuario: str = Field(..., description="ID/Usuario de 9 dígitos del campus")
    password: str = Field(..., description="Contraseña del usuario")

class ManualCaptchaRequest(BaseModel):
    usuario: str
    password: str
    codigo_manual: str

class NotasBuscarRequest(BaseModel):
    periodo: str = Field(default="2026-1")
    carrera: str = Field(default="Ingeniería de Sistemas")

class AutoCheckSetting(BaseModel):
    enabled: bool

class DeviceTokenRequest(BaseModel):
    fcm_token: str

@app.get("/")
def read_root():
    return {"message": "API de consulta UPAO Campus Virtual activa", "status": "ok"}

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
def get_periodos():
    now = datetime.now()
    year = now.year
    semestre = "1" if now.month < 8 else "2"
    periodo_actual = f"{year}-{semestre}"
    return {
        "periodo_actual": periodo_actual,
        "periodos": [
            f"{year}-2",
            f"{year}-1",
            f"{year-1}-2",
            f"{year-1}-1"
        ]
    }

@app.get("/notas/carreras")
def get_carreras():
    return {
        "carreras": [
            "Ingeniería de Sistemas",
            "Medicina Humana",
            "Derecho",
            "Administración"
        ]
    }

@app.post("/notas/buscar")
def buscar_notas(req: NotasBuscarRequest, authorization: str = Header(..., alias="Authorization")):
    token = authorization.replace("Bearer ", "").strip()
    result = scraper_service.get_notas(token, req.periodo, req.carrera)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
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
    notas = scraper_service.get_notas(token, "2026-1", "Ingeniería de Sistemas")
    
    user.ultimo_snapshot_notas = json.dumps(notas)
    db.commit()
    
    return {"success": True, "notas": notas}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
