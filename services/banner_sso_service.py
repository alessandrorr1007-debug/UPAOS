import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json

class BannerSSOService:
    def __init__(self):
        self.ssb_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        self.sso_login_url = "https://upaosso.upao.edu.pe:410/Account/Login"

    def login_sso(self, username: str, password: str) -> tuple[bool, str, requests.Session | None]:
        """
        Ejecuta el flujo completo de autenticación SSO (OAuth2 / WSO2):
        1. GET a ssb.upao.edu.pe para obtener URL de login y cookies de sesión.
        2. Extracción de inputs ocultos (sessionDataKey, state, etc.) del HTML.
        3. POST de credenciales a upaosso.upao.edu.pe.
        4. Seguimiento de redirecciones a commonauth y de vuelta a ssb.upao.edu.pe.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })

        try:
            # 1. Petición inicial a Banner SSB (Sigue redirecciones hacia upaosso.upao.edu.pe)
            print(f"[SSO Log] Iniciando flujo GET a: {self.ssb_url}")
            res_init = session.get(self.ssb_url, allow_redirects=True)
            print(f"[SSO Log] URL final tras redirecciones: {res_init.url}, HTTP Status: {res_init.status_code}")

            soup = BeautifulSoup(res_init.text, "html.parser")

            # 2. Extraer formulario y campos ocultos
            form = soup.find("form")
            action_url = self.sso_login_url
            if form and form.get("action"):
                action = form.get("action")
                action_url = urljoin(res_init.url, action)

            payload = {}
            for input_tag in soup.find_all("input"):
                name = input_tag.get("name")
                value = input_tag.get("value", "")
                if name:
                    payload[name] = value

            # Asignar usuario y contraseña (mapeando nombres comunes de campos)
            user_field_set = False
            pass_field_set = False

            for field_name in ["username", "Username", "txtUsername", "ctl00$txtUsuario", "user"]:
                if field_name in payload or soup.find("input", {"name": field_name}):
                    payload[field_name] = username
                    user_field_set = True
                    break

            for field_name in ["password", "Password", "txtPassword", "ctl00$txtClave", "pass"]:
                if field_name in payload or soup.find("input", {"name": field_name}):
                    payload[field_name] = password
                    pass_field_set = True
                    break

            if not user_field_set:
                payload["username"] = username
            if not pass_field_set:
                payload["password"] = password

            print(f"[SSO Log] Enviando POST a: {action_url} con campos: {list(payload.keys())}")

            # 3. POST de credenciales
            session.headers.update({"Referer": res_init.url})
            res_post = session.post(action_url, data=payload, allow_redirects=True)

            print(f"[SSO Log] Respuesta POST final: {res_post.url}, HTTP Status: {res_post.status_code}")

            # 4. Validar éxito (si retornó a ssb.upao.edu.pe y no se mantiene en la pantalla de login)
            if "studentGrades" in res_post.url or "ssb.upao.edu.pe" in res_post.url:
                print("[SSO Log] Login SSO Exitoso. Sesión autenticada creada.")
                return True, "Login SSO exitoso", session
            elif "Login" in res_post.url or "error" in res_post.text.lower():
                return False, "Usuario o contraseña incorrectos en el SSO de UPAO.", None
            else:
                return True, "Login SSO completado con éxito.", session

        except Exception as e:
            print(f"[SSO Error] Excepción en flujo SSO: {e}")
            return False, f"Error en conexión SSO: {str(e)}", None

    def get_student_grades_json(self, session: requests.Session, term: str = "202610") -> dict:
        """
        Consulta los endpoints REST de Ellucian Banner SSB para obtener los datos de notas en formato JSON.
        """
        try:
            # Endpoints comunes de Ellucian Banner SSB Student Grades API
            terms_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades/getTerms"
            grades_api_url = f"https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades/getStudentGrades?term={term}"

            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_url
            })

            res_grades = session.get(grades_api_url)
            print(f"[Banner Log] Consulta Notas JSON HTTP Status: {res_grades.status_code}")

            if res_grades.status_code == 200:
                try:
                    data = res_grades.json()
                    return {"success": True, "data": data}
                except Exception:
                    pass

            return {"success": False, "message": "No se obtuvieron datos JSON directos de Banner."}
        except Exception as e:
            return {"success": False, "message": f"Error consultando API de Banner: {e}"}

banner_sso_service = BannerSSOService()
