import os
import tempfile

os.environ["ADMIN_PASSWORD"] = "test-only-admin-password"

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test_admin_auth.db")

import main
from database import SessionLocal, UserSetting
from services import features_service
from services.auth_service import issue_token
from fastapi.testclient import TestClient

client = TestClient(main.app)

# Seed admin y un estudiante cualquiera
db = SessionLocal()
features_service.asegurar_admin(db)
if db.query(UserSetting).filter(UserSetting.usuario_campus == "000000001").first() is None:
    db.add(UserSetting(usuario_campus="000000001", password_encriptada="x"))
db.commit()
db.close()

ADMIN_TOKEN = issue_token("000000000")
STUDENT_TOKEN = issue_token("000000001")
NO_TOKEN = ""

def check(name, cond, extra=""):
    assert cond, name + " | " + extra
    print("OK " + name)

# 1. Sin token -> 401
for path, method in [
    ("/admin/cuentas", "get"),
    ("/admin/sugerencias", "get"),
    ("/admin/metricas", "get"),
]:
    r = getattr(client, method)(path, params={"admin_usuario": "000000000"})
    check(f"sin token {path} -> 401", r.status_code == 401, str(r.status_code))

# 2. Token de estudiante -> 403
for path, method in [
    ("/admin/cuentas", "get"),
    ("/admin/sugerencias", "get"),
    ("/admin/metricas", "get"),
]:
    r = getattr(client, method)(path, params={"admin_usuario": "000000000"}, headers={"Authorization": f"Bearer {STUDENT_TOKEN}"})
    check(f"estudiante {path} -> 403", r.status_code == 403, str(r.status_code))

# 3. Token admin pero admin_usuario distinto -> 403
r = client.get("/admin/cuentas", params={"admin_usuario": "000000001"}, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
check("admin_usuario no coincide -> 403", r.status_code == 403, str(r.status_code))

# 4. Token admin -> 200
for path, method in [
    ("/admin/cuentas", "get"),
    ("/admin/sugerencias", "get"),
    ("/admin/metricas", "get"),
]:
    r = getattr(client, method)(path, params={"admin_usuario": "000000000"}, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    check(f"admin {path} -> 200", r.status_code == 200, str(r.status_code))

# 5. PATCH estado sin token -> 401 ; con admin -> 200/400 (no 401/403)
r = client.patch("/admin/sugerencias/1/estado", json={"estado": "visto"}, params={"admin_usuario": "000000000"})
check("patch sin token -> 401", r.status_code == 401, str(r.status_code))
r = client.patch("/admin/sugerencias/1/estado", json={"estado": "visto"}, params={"admin_usuario": "000000000"}, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
check("patch admin -> no 401/403", r.status_code in (200, 400, 404), str(r.status_code))

# 6. POST /semana sin token -> 401 ; con admin -> 200
r = client.post("/admin/semana", json={"fecha_inicio": "2026-03-02"}, params={"admin_usuario": "000000000"})
check("semana sin token -> 401", r.status_code == 401, str(r.status_code))
r = client.post("/admin/semana", json={"fecha_inicio": "2026-03-02"}, params={"admin_usuario": "000000000"}, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
check("semana admin -> 200", r.status_code == 200, str(r.json()))

# 7. /admin/login devuelve token uniforme sess_
r = client.post("/admin/login", json={"usuario": "000000000", "password": "test-only-admin-password"})
check("admin/login token sess_", r.status_code == 200 and r.json()["token"].startswith("sess_"), str(r.json()))

print("AUTH DONE")
