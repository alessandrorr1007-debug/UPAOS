import base64
import requests
from bs4 import BeautifulSoup
from config import settings
from services.ocr_service import process_captcha_ocr
from services.banner_sso_service import banner_sso_service

ACTIVE_SESSIONS: dict[str, requests.Session] = {}

class CampusScraperService:
    def __init__(self):
        self.login_url = settings.CAMPUS_URL
        self.captcha_url = settings.CAPTCHA_URL
        self.notas_url = settings.NOTAS_URL

    def login(self, username: str, password: str, manual_captcha: str | None = None) -> dict:
        """
        Método unificado de login:
        1. Intenta primero el nuevo flujo oficial Ellucian Banner SSB (SSO sin Captcha).
        2. Si falla o está en mantenimiento, intenta el flujo legado ASP.NET WebForms con OCR.
        """
        print(f"[Scraper] Intentando inicio de sesión vía Banner SSB SSO para usuario: {username}")
        success, msg, session = banner_sso_service.login_sso(username, password)

        if success and session is not None:
            token = f"sess_{username}_{base64.b64encode(username.encode()).decode()[:10]}"
            ACTIVE_SESSIONS[token] = session
            return {
                "success": True,
                "token": token,
                "necesita_captcha": False,
                "message": "Login SSO exitoso sin captcha."
            }

        print(f"[Scraper] SSO falló ('{msg}'). Intentando fallback legado ASP.NET WebForms con OCR...")
        return self._login_legacy(username, password, manual_captcha)

    def _login_legacy(self, username: str, password: str, manual_captcha: str | None = None) -> dict:
        session, form_fields, captcha_bytes = self.initialize_login_session()
        
        captcha_code = manual_captcha
        if not captcha_code:
            captcha_code = process_captcha_ocr(captcha_bytes)
            
        if not captcha_code:
            img_b64 = base64.b64encode(captcha_bytes).decode("utf-8")
            return {
                "success": False,
                "necesita_captcha": True,
                "imagen_base64": img_b64,
                "message": "No se pudo reconocer el captcha automáticamente. Ingrese el código manualmente."
            }

        payload = {
            **form_fields,
            "txtUsuario": username,
            "txtClave": password,
            "txtCaptcha": captcha_code,
            "btnIngresar": "Ingresar"
        }
        
        post_res = session.post(self.login_url, data=payload)
        
        if "login.aspx" not in post_res.url and post_res.status_code == 200:
            token = f"sess_{username}_{base64.b64encode(username.encode()).decode()[:10]}"
            ACTIVE_SESSIONS[token] = session
            return {
                "success": True,
                "token": token,
                "necesita_captcha": False,
                "message": "Login legado exitoso."
            }
        else:
            try:
                fresh_captcha = session.get(self.captcha_url, headers={"Referer": self.login_url}).content
                fresh_b64 = base64.b64encode(fresh_captcha).decode("utf-8")
            except Exception:
                fresh_b64 = base64.b64encode(captcha_bytes).decode("utf-8")

            return {
                "success": False,
                "necesita_captcha": True,
                "imagen_base64": fresh_b64,
                "message": "Código o credenciales incorrectos."
            }

    def initialize_login_session(self) -> tuple[requests.Session, dict, bytes]:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        response = session.get(self.login_url)
        soup = BeautifulSoup(response.text, "html.parser")
        
        viewstate = soup.find("input", {"id": "__VIEWSTATE"})
        eventvalidation = soup.find("input", {"id": "__EVENTVALIDATION"})
        viewstategenerator = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
        
        form_data = {
            "__VIEWSTATE": viewstate.get("value", "") if viewstate else "",
            "__EVENTVALIDATION": eventvalidation.get("value", "") if eventvalidation else "",
            "__VIEWSTATEGENERATOR": viewstategenerator.get("value", "") if viewstategenerator else "",
        }
        
        captcha_res = session.get(self.captcha_url, headers={"Referer": self.login_url})
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
