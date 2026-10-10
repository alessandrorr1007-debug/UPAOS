"""Offline regression tests: python -m unittest test_security -v."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

TEST_DIRECTORY = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(TEST_DIRECTORY.name, "security.db")
os.environ["ADMIN_PASSWORD"] = "test-only-admin-password"

import requests
import main
from fastapi.testclient import TestClient
from database import AuthSession, SessionLocal, UserSetting, encrypt_password, decrypt_password, engine, _migrate_legacy_encryption
from cryptography.fernet import Fernet
from services import features_service
from services.auth_service import issue_token, token_user, _digest
from services.scraper_service import ACTIVE_SESSIONS, scraper_service


def tearDownModule():
    engine.dispose()
    TEST_DIRECTORY.cleanup()


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with SessionLocal() as db:
            features_service.asegurar_admin(db)
            for usuario in ("000000001", "000000002"):
                db.add(UserSetting(usuario_campus=usuario, password_encriptada=encrypt_password("test-pass")))
            db.commit()

    def setUp(self):
        self.client = TestClient(main.app)
        self.token = issue_token("000000001")
        self.headers = {"Authorization": "Bearer " + self.token}

    def test_tokens_are_unpredictable_and_only_hash_is_stored(self):
        another = issue_token("000000001")
        self.assertNotEqual(self.token, another)
        self.assertNotIn("000000001", self.token)
        with SessionLocal() as db:
            self.assertIsNotNone(db.get(AuthSession, _digest(self.token)))
            self.assertIsNone(db.get(AuthSession, self.token))

    def test_forged_and_expired_tokens_are_rejected(self):
        for token in ("sess_000000000_admin", "sess_000000001_fake", "invalid"):
            response = self.client.get("/admin/cuentas", headers={"Authorization": "Bearer " + token})
            self.assertEqual(response.status_code, 401)
        with SessionLocal() as db:
            db.get(AuthSession, _digest(self.token)).expires_at = datetime.utcnow() - timedelta(seconds=1)
            db.commit()
        self.assertEqual(self.client.get("/cuenta", params={"usuario": "000000001"}, headers=self.headers).status_code, 401)

    def test_all_private_routes_require_authentication(self):
        for route in main.app.routes:
            if not hasattr(route, "methods") or route.path in {"/", "/healthz", "/login", "/login/confirmar-captcha", "/admin/login", "/semana", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}:
                continue
            method = next(iter(route.methods))
            path = route.path.replace("{notificacion_id}", "1").replace("{sugerencia_id}", "1").replace("{periodo}", "202610")
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path, json={}).status_code, 401)

    def test_cross_account_reads_and_writes_are_rejected(self):
        cases = [("GET", "/cuenta", None), ("GET", "/notificaciones", None),
                 ("PATCH", "/settings/auto-check", {"enabled": True}),
                 ("POST", "/device-token", {"fcm_token": "other-device"}),
                 ("POST", "/notas/actualizar-ahora", None)]
        for method, path, body in cases:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path, params={"usuario": "000000002"}, json=body, headers=self.headers).status_code, 403)
        for path, body in [("/sugerencias", {"usuario": "000000002", "texto": "Una sugerencia válida"}), ("/ranking/optin", {"usuario": "000000002", "enabled": True})]:
            self.assertEqual(self.client.post(path, json=body, headers=self.headers).status_code, 403)

    def test_own_account_contracts_are_preserved(self):
        response = self.client.patch("/settings/auto-check", params={"usuario": "000000001"}, json={"enabled": True}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["auto_check_enabled"])
        response = self.client.get("/notificaciones", params={"usuario": "000000001"}, headers=self.headers)
        self.assertEqual(response.json(), {"no_leidas": 0, "total": 0, "notificaciones": []})
        self.assertEqual(self.client.post("/sugerencias", json={"usuario": "000000001", "texto": "Una sugerencia válida para la app"}, headers=self.headers).status_code, 200)

    def test_admin_login_and_permissions(self):
        response = self.client.post("/admin/login", json={"usuario": features_service.ADMIN_USUARIO, "password": "test-only-admin-password"})
        self.assertEqual(response.status_code, 200)
        headers = {"Authorization": "Bearer " + response.json()["token"]}
        self.assertEqual(self.client.get("/admin/cuentas", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/admin/cuentas", headers=self.headers).status_code, 403)
        self.assertEqual(self.client.post("/admin/login", json={"usuario": features_service.ADMIN_USUARIO, "password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/login", json={"usuario": features_service.ADMIN_USUARIO, "password": "wrong"}).status_code, 401)

    def test_admin_seed_preserves_existing_password(self):
        with SessionLocal() as db:
            user = db.get(UserSetting, features_service.ADMIN_USUARIO)
            original = user.admin_password_hash
            features_service.asegurar_admin(db)
            self.assertEqual(user.admin_password_hash, original)

    def test_session_survives_banner_memory_loss_and_renews(self):
        ACTIVE_SESSIONS.clear()
        self.assertEqual(token_user(self.token), "000000001")
        session = requests.Session()
        with patch.object(main.banner_sso_service, "login_sso", return_value=(True, "ok", session)):
            with SessionLocal() as db:
                self.assertIs(main._sesion_garantizada(self.token, db), session)
        self.assertIs(ACTIVE_SESSIONS[self.token], session)

    def test_student_login_uses_existing_response_contract(self):
        with patch.object(main.banner_sso_service, "login_sso", return_value=(True, "ok", requests.Session())), patch.object(features_service, "extraer_nombre_estudiante", return_value="Estudiante"):
            response = self.client.post("/login", json={"usuario": "000000001", "password": "test-pass"})
        self.assertTrue(response.json()["success"])
        self.assertEqual(token_user(response.json()["token"]), "000000001")
        with SessionLocal() as db:
            self.assertEqual(decrypt_password(db.get(UserSetting, "000000001").password_encriptada), "test-pass")

    def test_old_default_encryption_is_migrated_without_losing_password(self):
        if main.settings.FERNET_KEY:
            self.skipTest("Migration only applies to databases without an explicit key")
        legacy = Fernet(b"AekYrdvES-txYMoPb6t1YiBMEyoE26ZmrwgJOTiMv3Q=")
        with SessionLocal() as db:
            db.get(UserSetting, "000000002").password_encriptada = legacy.encrypt(b"legacy-password").decode()
            db.commit()
        _migrate_legacy_encryption()
        _migrate_legacy_encryption()
        with SessionLocal() as db:
            self.assertEqual(decrypt_password(db.get(UserSetting, "000000002").password_encriptada), "legacy-password")


if __name__ == "__main__":
    unittest.main()
