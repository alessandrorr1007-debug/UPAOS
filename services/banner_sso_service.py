import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import json

class BannerSSOService:
    def __init__(self):
        self.ssb_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        self.sso_login_url = "https://upaosso.upao.edu.pe:410/Account/Login"

    def login_sso(self, username: str, password: str) -> tuple[bool, str, requests.Session | None]:
        """
        Ejecuta el flujo completo de autenticación SSO (OAuth2 / WSO2):
        1. GET a ssb.upao.edu.pe para obtener URL de login, __RequestVerificationToken y cookies de sesión.
        2. Mapeo exacto de campos: id_usuario, nip, __RequestVerificationToken y hidden inputs OAuth2.
        3. POST de credenciales a upaosso.upao.edu.pe:410.
        4. Verificación estricta de parámetros de error (is_error / mensaje_error) en la URL final.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })

        try:
            # 1. Petición inicial a Banner SSB (Redirige hacia upaosso.upao.edu.pe)
            print(f"[SSO Log] Iniciando flujo GET a: {self.ssb_url}")
            res_init = session.get(self.ssb_url, allow_redirects=True)
            print(f"[SSO Log] URL final tras redirecciones: {res_init.url}, HTTP Status: {res_init.status_code}")

            soup = BeautifulSoup(res_init.text, "html.parser")

            # 2. Determinar la URL del POST y mapear los campos del formulario
            form = soup.find("form")
            action_url = res_init.url
            if form and form.get("action"):
                action = form.get("action")
                action_url = urljoin(res_init.url, action)

            payload = {}
            for input_tag in soup.find_all("input"):
                name = input_tag.get("name")
                value = input_tag.get("value", "")
                if name:
                    payload[name] = value

            # Mapeo exacto confirmado: id_usuario y nip (elimina campos innecesarios como username/password)
            payload["id_usuario"] = username
            payload["nip"] = password
            payload["btn_valida"] = "Iniciar sesión"

            # Limpiar campos duplicados/inválidos si existieran
            payload.pop("username", None)
            payload.pop("password", None)

            # Verificar token de verificación antiforgery
            verification_token = payload.get("__RequestVerificationToken")
            print(f"[SSO Log] Token __RequestVerificationToken extraído: {verification_token[:20]}..." if verification_token else "[SSO Warning] Token __RequestVerificationToken no encontrado")

            print(f"[SSO Log] Enviando POST a: {action_url} con campos: {list(payload.keys())}")

            # 3. POST de credenciales
            session.headers.update({"Referer": res_init.url})
            res_post = session.post(action_url, data=payload, allow_redirects=True)

            print(f"[SSO Log] Respuesta POST final: {res_post.url}, HTTP Status: {res_post.status_code}")

            # 4. Parsea y valida los parámetros de la URL final para verificar si hubo error
            parsed_url = urlparse(res_post.url)
            query_params = parse_qs(parsed_url.query)

            is_error_str = query_params.get("is_error", [None])[0] or query_params.get("isError", [None])[0]
            mensaje_error = query_params.get("mensaje_error", [None])[0] or query_params.get("mensajeError", [None])[0] or query_params.get("error", [None])[0]

            is_error = is_error_str is not None and is_error_str.lower() == "true"

            if is_error or mensaje_error:
                error_msg_decoded = unquote(mensaje_error) if mensaje_error else "Error en credenciales del SSO UPAO"
                print(f"[SSO Error Log] Fallo detectado en URL. Error: {error_msg_decoded}")
                return False, error_msg_decoded, None

            # Confirmar que la sesión retornó a ssb.upao.edu.pe o studentGrades
            if "studentGrades" in res_post.url or "ssb.upao.edu.pe" in res_post.url:
                print("[SSO Log] Login SSO Exitoso. Sesión autenticada creada.")
                return True, "Login SSO exitoso sin captcha", session

            if "upaosso" in res_post.url or "Login" in res_post.url:
                return False, "Credenciales o PIN (nip) incorrectos en SSO UPAO", None

            return True, "Login SSO completado con éxito", session

        except Exception as e:
            print(f"[SSO Error] Excepción en flujo SSO: {e}")
            return False, f"Error en conexión SSO: {str(e)}", None

    def get_student_grades_json(self, session: requests.Session, term: str = "202610") -> dict:
        """
        Consulta los endpoints REST de Ellucian Banner SSB para obtener los datos de notas en formato JSON.
        """
        try:
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
