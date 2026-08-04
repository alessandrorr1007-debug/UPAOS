import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test_features.db")

import main
from database import SessionLocal, UserSetting
from services import features_service
from fastapi.testclient import TestClient

client = TestClient(main.app)

def check(name, cond, extra=""):
    print(("OK " if cond else "FAIL ") + name + (" | " + extra if extra else ""))

# 1. /semana sin configurar
r = client.get("/semana")
check("semana sin configurar", r.status_code == 200 and r.json()["configurada"] is False, str(r.json()))

# 2. establecer inicio de ciclo via service
db = SessionLocal()
features_service.establecer_semana_inicio(db, "2026-03-02")
db.close()
r = client.get("/semana")
check("semana configurada", r.status_code == 200 and r.json()["configurada"] is True, r.json()["etiqueta"])

# 3. cuenta inexistente -> 404
r = client.get("/cuenta", params={"usuario": "999999999"})
check("cuenta 404", r.status_code == 404, str(r.status_code))

# 4. crear usuario + /cuenta
db = SessionLocal()
db.add(UserSetting(usuario_campus="000000001", password_encriptada="x"))
db.commit()
db.close()
r = client.get("/cuenta", params={"usuario": "000000001"})
check("cuenta ok", r.status_code == 200 and r.json()["usuario"] == "000000001", str(r.json()))

# 5. sugerencia corta -> 400
r = client.post("/sugerencias", json={"usuario": "000000001", "texto": "abc"})
check("sugerencia corta 400", r.status_code == 400, str(r.status_code))

# 6. sugerencia valida
r = client.post("/sugerencias", json={"usuario": "000000001", "texto": "Me gustaria una pestaña de promedios por ciclo"})
check("sugerencia ok", r.status_code == 200 and r.json().get("success"), str(r.json()))

# 7. anti-spam: 2 mas -> 4a debe dar 400
for i in range(2):
    client.post("/sugerencias", json={"usuario": "000000001", "texto": f"Otra sugerencia numero {i} con texto suficiente largo para pasar"})
r = client.post("/sugerencias", json={"usuario": "000000001", "texto": "Cuarta sugerencia que ya excede el limite diario de tres"})
check("anti-spam 400", r.status_code == 400 and "Límite" in r.json()["detail"], str(r.json()))

# 8. mis sugerencias
r = client.get("/sugerencias/mis", params={"usuario": "000000001"})
check("mis sugerencias 3", r.status_code == 200 and len(r.json()["sugerencias"]) == 3, str(len(r.json()["sugerencias"])))

# 9. ranking optin sin usuario -> 404
r = client.post("/ranking/optin", json={"usuario": "999999999", "enabled": True})
check("optin 404", r.status_code == 404, str(r.status_code))

# 10. ranking optin on
r = client.post("/ranking/optin", json={"usuario": "000000001", "enabled": True})
check("optin on", r.status_code == 200 and r.json()["ranking_optin"] is True, str(r.json()))

# 11. ranking sin datos -> insuficientes
r = client.get("/ranking", params={"usuario": "000000001", "course_id": "HUMA-1185", "ciclo": "202610"})
check("ranking insuficientes", r.json().get("motivo") == "insuficientes", str(r.json()))

# 12. registrar cursos ranking (opt-in activo) y repetir para otros usuarios
db = SessionLocal()
for u in ["000000001", "000000002", "000000003", "000000004", "000000005"]:
    us = db.query(UserSetting).filter(UserSetting.usuario_campus == u).first()
    if us is None:
        db.add(UserSetting(usuario_campus=u, password_encriptada="x", ranking_optin=True))
    else:
        us.ranking_optin = True
db.commit()
cursos = [
    {"course_id": "HUMA-1185", "course_name": "Comunicacion", "nota": 16.5},
    {"course_id": "HUMA-1185", "course_name": "Comunicacion", "nota": 14.0},
    {"course_id": "HUMA-1185", "course_name": "Comunicacion", "nota": 18.0},
    {"course_id": "HUMA-1185", "course_name": "Comunicacion", "nota": 12.5},
    {"course_id": "HUMA-1185", "course_name": "Comunicacion", "nota": 15.0},
]
for i, c in enumerate(cursos):
    features_service.registrar_cursos_ranking(db, f"00000000{i+1}", "202610", [c])
db.close()

# 13. ranking con 5 -> posicion de 000000003 (18.0) debe ser 1
r = client.get("/ranking", params={"usuario": "000000003", "course_id": "HUMA-1185", "ciclo": "202610"})
check("ranking pos1", r.json()["disponible"] and r.json()["position"] == 1, str(r.json()))
r = client.get("/ranking", params={"usuario": "000000001", "course_id": "HUMA-1185", "ciclo": "202610"})
check("ranking 16.5 pos2", r.json()["position"] == 2, str(r.json()))

# 14. DAU serie y actividad
client.get("/cuenta", params={"usuario": "000000001"})
client.get("/semana")
db = SessionLocal()
dau = features_service.serie_dau(db, 30)
act = features_service.cuentas_activas_hoy(db)
db.close()
check("serie_dau 30 dias", len(dau) == 30 and act >= 1, f"activos_hoy={act}")

# 15. seed admin idempotente
db = SessionLocal()
features_service.asegurar_admin(db)
admin = db.query(UserSetting).filter(UserSetting.usuario_campus == "000002006").first()
check("seed admin", admin is not None and admin.is_admin and admin.admin_password_hash, "")
check("verificar admin pass ok", features_service.verificar_password_admin(admin, "AlessandroAdmin"), "")
check("verificar admin pass mal", not features_service.verificar_password_admin(admin, "wrong"), "")
features_service.asegurar_admin(db)
db.close()
check("seed admin idempotente", True, "")

print("SMOKE DONE")
