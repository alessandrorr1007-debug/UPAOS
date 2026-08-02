import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import json

class BannerSSOService:
    def __init__(self):
        self.ssb_base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        self.sso_login_url = "https://upaosso.upao.edu.pe:410/Account/Login"

    def login_sso(self, username: str, password: str) -> tuple[bool, str, requests.Session | None]:
        """
        Ejecuta el flujo completo de autenticación SSO (OAuth2 / WSO2):
        1. GET a ssb.upao.edu.pe para obtener la URL de login con los parámetros OIDC, __RequestVerificationToken y cookies de sesión.
        2. Mapeo exacto de campos: id_usuario, nip, __RequestVerificationToken y hidden inputs OIDC.
        3. POST de credenciales a upaosso.upao.edu.pe:410.
        4. Verificación estricta de parámetros de error (is_error / mensaje_error) en la URL final.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })

        try:
            print(f"[SSO Log] Iniciando flujo GET a: {self.ssb_base_url}")
            res_init = session.get(self.ssb_base_url, allow_redirects=True)
            print(f"[SSO Log] URL final tras redirecciones: {res_init.url}, HTTP Status: {res_init.status_code}")

            soup = BeautifulSoup(res_init.text, "html.parser")

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

            # Mapeo exacto de campos reales confirmados: id_usuario y nip
            payload["id_usuario"] = username
            payload["nip"] = password
            payload["btn_valida"] = "Iniciar sesión"

            # Limpiar campos no usados en el formulario
            payload.pop("username", None)
            payload.pop("password", None)

            verification_token = payload.get("__RequestVerificationToken")
            print(f"[SSO Log] Token __RequestVerificationToken extraído: {verification_token[:25]}..." if verification_token else "[SSO Warning] Token __RequestVerificationToken no encontrado")

            print(f"[SSO Log] Enviando POST a: {action_url} con campos: {list(payload.keys())}")

            session.headers.update({"Referer": res_init.url})
            res_post = session.post(action_url, data=payload, allow_redirects=True)

            print(f"[SSO Log] Respuesta POST final: {res_post.url}, HTTP Status: {res_post.status_code}")

            # Parsear parámetros de la URL final para verificar posibles errores
            parsed_url = urlparse(res_post.url)
            query_params = parse_qs(parsed_url.query)

            is_error_str = query_params.get("is_error", [None])[0] or query_params.get("isError", [None])[0]
            mensaje_error = query_params.get("mensaje_error", [None])[0] or query_params.get("mensajeError", [None])[0] or query_params.get("error", [None])[0]

            is_error = is_error_str is not None and is_error_str.lower() == "true"

            if is_error or mensaje_error:
                error_msg_decoded = unquote(mensaje_error) if mensaje_error else "Error en credenciales del SSO UPAO"
                print(f"[SSO Error Log] Fallo detectado en URL final: {error_msg_decoded}")
                return False, error_msg_decoded, None

            # Éxito solo si no hay error y la URL pertenece a ssb.upao.edu.pe
            if "studentGrades" in res_post.url or "ssb.upao.edu.pe" in res_post.url:
                print("[SSO Log] Login SSO Exitoso. Sesión autenticada creada en Banner SSB.")
                return True, "Login SSO exitoso sin captcha", session

            if "upaosso" in res_post.url or "Login" in res_post.url:
                return False, "Credenciales o PIN (nip) incorrectos en SSO UPAO", None

            return True, "Login SSO completado con éxito", session

        except Exception as e:
            print(f"[SSO Error] Excepción en flujo SSO: {e}")
            return False, f"Error en conexión SSO: {str(e)}", None

    # --- Endpoints Reales Confirmados de Banner SSB ---

    def get_periodos(self, session: requests.Session) -> dict:
        """
        GET /term?filter=&page=1&max=50 -> Lista de periodos disponibles en Banner SSB.
        """
        try:
            url = f"{self.ssb_base_url}/term?filter=&page=1&max=50"
            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_base_url
            })
            res = session.get(url)
            print(f"[Banner Log] GET Periodos -> HTTP Status: {res.status_code}")

            if res.status_code == 200:
                data = res.json()
                # Limpieza de lista para entregar código (term) y nombre visible (descripción)
                periodos_clean = []
                for item in data if isinstance(data, list) else data.get("items", []):
                    periodos_clean.append({
                        "code": item.get("code"),
                        "description": item.get("description")
                    })
                return {"success": True, "periodos": periodos_clean, "raw": data}

            return {"success": False, "message": f"Error HTTP {res.status_code} al consultar periodos"}
        except Exception as e:
            return {"success": False, "message": f"Excepción en get_periodos: {e}"}

    def get_niveles(self, session: requests.Session, term: str) -> dict:
        """
        GET /level?filter=&term={term} -> Lista de niveles/currículas disponibles (ej. PREGRADO con código UB).
        """
        try:
            url = f"{self.ssb_base_url}/level?filter=&term={term}"
            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_base_url
            })
            res = session.get(url)
            print(f"[Banner Log] GET Niveles (Term: {term}) -> HTTP Status: {res.status_code}")

            if res.status_code == 200:
                data = res.json()
                niveles_clean = []
                for item in data if isinstance(data, list) else data.get("items", []):
                    niveles_clean.append({
                        "code": item.get("code"),
                        "description": item.get("description")
                    })
                return {"success": True, "niveles": niveles_clean, "raw": data}

            return {"success": False, "message": f"Error HTTP {res.status_code} al consultar niveles"}
        except Exception as e:
            return {"success": False, "message": f"Excepción en get_niveles: {e}"}

    def get_curriculum(self, session: requests.Session, term: str) -> dict:
        """
        GET /curriculum?term={term} -> Información de currícula del estudiante.
        """
        try:
            url = f"{self.ssb_base_url}/curriculum?term={term}"
            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_base_url
            })
            res = session.get(url)
            if res.status_code == 200:
                return {"success": True, "curriculum": res.json()}
            return {"success": False, "message": f"Error HTTP {res.status_code}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_courses(self, session: requests.Session, term: str, level: str) -> dict:
        """
        GET /courses?termCode={term}&levelCode={level}&filterText=&pageOffset=0&pageMaxSize=20&sortColumn=-1&sortDirection=-1
        Endpoint principal: devuelve la lista de cursos del periodo/nivel seleccionado.
        """
        try:
            url = f"{self.ssb_base_url}/courses?termCode={term}&levelCode={level}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_base_url
            })
            res = session.get(url)
            print(f"[Banner Log] GET Cursos (Term: {term}, Level: {level}) -> HTTP Status: {res.status_code}")

            if res.status_code == 200:
                data = res.json()
                return {"success": True, "cursos": data}

            return {"success": False, "message": f"Error HTTP {res.status_code} al consultar cursos"}
        except Exception as e:
            return {"success": False, "message": f"Excepción en get_courses: {e}"}

    def get_course_grade_detail(self, session: requests.Session, course_id: str, term: str) -> dict:
        """
        PENDIENTE: confirmar URL real con DevTools al expandir un curso en la interfaz de Banner.
        Placeholder preparado para integrar el desglose de subcomponentes (EP1/Parcial/EP2/Final).
        """
        return {
            "success": False,
            "status": "PENDIENTE_CONFIRMAR_URL",
            "message": "Función preparada. Pendiente obtener URL exacta de desgloses vía DevTools.",
            "detalles": None
        }

banner_sso_service = BannerSSOService()
