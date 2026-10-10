import base64
import secrets
import time
from threading import Lock
import requests
from bs4 import BeautifulSoup
from config import settings
from services.ocr_service import process_captcha_ocr
from services.banner_sso_service import banner_sso_service
from services.auth_service import issue_token

ACTIVE_SESSIONS: dict[str, requests.Session] = {}
USER_SESSION_TOKENS: dict[str, str] = {}

def _token_para(username: str) -> str:
    token = issue_token(username)
    USER_SESSION_TOKENS[username] = token
    return token

class CampusScraperService:
    def __init__(self):
        self.login_url = settings.CAMPUS_URL
        self.captcha_url = settings.CAPTCHA_URL
        self.notas_url = settings.NOTAS_URL
        self._captcha_challenges = {}
        self._captcha_lock = Lock()

    def login(self, username: str, password: str, manual_captcha: str | None = None, captcha_id: str | None = None) -> dict:
        """
        Método unificado de login:
        1. Intenta primero el nuevo flujo oficial Ellucian Banner SSB (SSO sin Captcha).
        2. Si falla o está en mantenimiento, intenta el flujo legado ASP.NET WebForms con OCR.
        """
        if manual_captcha is not None:
            try:
                return self._login_legacy(username, password, manual_captcha, captcha_id)
            except requests.RequestException:
                return self._login_error("service_unavailable", "No se pudo conectar con UPAO. Inténtalo nuevamente en unos minutos.")
        print(f"[Scraper] Intentando inicio de sesión vía Banner SSB SSO para usuario: {username}")
        success, msg, session = banner_sso_service.login_sso(username, password)

        if success and session is not None:
            token = _token_para(username)
            ACTIVE_SESSIONS[token] = session
            return {
                "success": True,
                "token": token,
                "necesita_captcha": False,
                "message": "Login SSO exitoso sin captcha."
            }

        if msg == "invalid_credentials" or any(word in msg.lower() for word in ("incorrect", "credenciales", "inválid", "invalid")):
            return self._login_error("invalid_credentials", "ID o contraseña incorrectos. Revisa tus datos.")
        print("[Scraper] SSO no disponible. Intentando portal alternativo.")
        try:
            return self._login_legacy(username, password)
        except requests.RequestException:
            return self._login_error("service_unavailable", "No se pudo conectar con UPAO. Inténtalo nuevamente en unos minutos.")

    @staticmethod
    def _login_error(code: str, message: str) -> dict:
        return {"success": False, "necesita_captcha": False, "error_code": code, "message": message}

    def _captcha_response(self, username, session, form_fields, captcha_bytes):
        challenge_id = secrets.token_urlsafe(24)
        with self._captcha_lock:
            now = time.monotonic()
            for key, challenge in list(self._captcha_challenges.items()):
                if challenge[3] <= now:
                    self._captcha_challenges.pop(key)[1].close()
            # Bound memory even when the alternate portal is unavailable for a long time.
            if len(self._captcha_challenges) >= 100:
                oldest = next(iter(self._captcha_challenges))
                self._captcha_challenges.pop(oldest)[1].close()
            self._captcha_challenges[challenge_id] = (username, session, form_fields, now + 300)
        return {"success": False, "necesita_captcha": True, "error_code": "captcha_required",
                "captcha_id": challenge_id, "imagen_base64": base64.b64encode(captcha_bytes).decode(),
                "message": "Ingresa el código de la imagen para continuar."}

    def _sesion_sigue_valida(self, session: requests.Session) -> bool:
        """
        Comprueba rápido (1 GET a /term) que la sesión de Banner sigue autenticada.
        Válida si responde 200 con JSON y NO redirige a la página de login.
        """
        if session is None:
            return False
        try:
            probe = session.get(
                f"{banner_sso_service.ssb_base_url}/term?filter=&page=1&max=5",
                timeout=12,
                allow_redirects=True,
            )
            if probe.status_code != 200:
                return False
            if "login" in probe.url.lower():
                return False
            content_type = probe.headers.get("content-type", "")
            if "json" not in content_type.lower():
                return False
            return True
        except Exception as e:
            print(f"[Scraper] Excepción validando sesión: {e}")
            return False

    def obtener_sesion_valida(self, username: str, password: str) -> tuple[requests.Session | None, str | None]:
        """
        Optimización clave para el chequeo de 10 min: reutiliza la sesión
        autenticada guardada en ACTIVE_SESSIONS si sigue válida (1 GET a /term).
        Solo si expiró se hace el login completo de nuevo.
        Devuelve (session, token) o (None, None).
        """
        token = USER_SESSION_TOKENS.get(username)
        session = ACTIVE_SESSIONS.get(token)
        if session is not None and self._sesion_sigue_valida(session):
            print(f"[Scraper] Sesión de {username} reutilizada sin login completo.")
            return session, token

        print(f"[Scraper] Sesión de {username} expirada o ausente. Haciendo login completo...")
        result = self.login(username, password)
        if result.get("success"):
            new_token = result.get("token")
            return ACTIVE_SESSIONS.get(new_token), new_token
        print(f"[Scraper] Login completo falló para {username}: {result.get('message')}")
        return None, None

    def _login_legacy(self, username: str, password: str, manual_captcha: str | None = None, captcha_id: str | None = None) -> dict:
        if manual_captcha is not None:
            with self._captcha_lock:
                challenge = self._captcha_challenges.pop(captcha_id, None)
            if challenge is None:
                return self._login_error("captcha_expired", "El código de verificación venció. Inicia sesión nuevamente.")
            owner, session, form_fields, expires_at = challenge
            if owner != username or expires_at <= time.monotonic():
                session.close()
                return self._login_error("captcha_expired", "El código de verificación venció. Inicia sesión nuevamente.")
            captcha_bytes = b""
        else:
            session, form_fields, captcha_bytes = self.initialize_login_session()
        
        captcha_code = manual_captcha
        if not captcha_code:
            captcha_code = process_captcha_ocr(captcha_bytes)
            
        if not captcha_code:
            return self._captcha_response(username, session, form_fields, captcha_bytes)

        payload = {
            **form_fields,
            "txtUsuario": username,
            "txtClave": password,
            "txtCaptcha": captcha_code,
            "btnIngresar": "Ingresar"
        }
        
        post_res = session.post(self.login_url, data=payload, timeout=30)
        post_res.raise_for_status()
        
        if "login.aspx" not in post_res.url and post_res.status_code == 200:
            token = _token_para(username)
            ACTIVE_SESSIONS[token] = session
            return {
                "success": True,
                "token": token,
                "necesita_captcha": False,
                "message": "Login legado exitoso."
            }
        session.close()
        return self._login_error("invalid_credentials", "ID, contraseña o código incorrectos. Revisa tus datos.")

    def initialize_login_session(self) -> tuple[requests.Session, dict, bytes]:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        response = session.get(self.login_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        viewstate = soup.find("input", {"id": "__VIEWSTATE"})
        eventvalidation = soup.find("input", {"id": "__EVENTVALIDATION"})
        viewstategenerator = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
        
        form_data = {
            "__VIEWSTATE": viewstate.get("value", "") if viewstate else "",
            "__EVENTVALIDATION": eventvalidation.get("value", "") if eventvalidation else "",
            "__VIEWSTATEGENERATOR": viewstategenerator.get("value", "") if viewstategenerator else "",
        }
        
        captcha_res = session.get(self.captcha_url, headers={"Referer": self.login_url}, timeout=30)
        captcha_bytes = captcha_res.content
        
        return session, form_data, captcha_bytes

    def get_notas(self, token: str, periodo: str, carrera: str) -> dict:
        session = ACTIVE_SESSIONS.get(token)
        if not session:
            return {"error": "Sesión no encontrada o expirada. Vuelva a iniciar sesión."}

        # Probar primero la extracción JSON de Banner SSB
        banner_json = banner_sso_service.get_student_grades_json(session, term=periodo)
        if banner_json.get("success"):
            return {
                "periodo": periodo,
                "carrera": carrera,
                "cursos": banner_json.get("data", [])
            }

        # Fallback a scraping HTML tradicional de notas
        res = session.get(self.notas_url)
        soup = BeautifulSoup(res.text, "html.parser")
        
        cursos = []
        rows = soup.find_all("tr", class_=["fila_nota", "gridRow"])
        
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 5:
                nombre = cols[0].text.strip()
                ep1_val = cols[1].text.strip()
                parcial_val = cols[2].text.strip()
                ep2_val = cols[3].text.strip()
                final_val = cols[4].text.strip()
                
                cursos.append({
                    "nombre": nombre,
                    "ep1": {
                        "nota": ep1_val,
                        "detalles": []
                    },
                    "parcial": parcial_val,
                    "ep2": {
                        "nota": ep2_val,
                        "detalles": []
                    },
                    "final": final_val
                })

        return {
            "periodo": periodo,
            "carrera": carrera,
            "cursos": cursos
        }

scraper_service = CampusScraperService()
