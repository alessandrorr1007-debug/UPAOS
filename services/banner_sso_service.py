import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import json

class BannerSSOService:
    def __init__(self):
        self.ssb_base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        self.sso_login_url = "https://upaosso.upao.edu.pe:410/Account/Login"

    def login_sso(self, username: str, password: str) -> tuple[bool, str, requests.Session | None]:
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

            payload["id_usuario"] = username
            payload["nip"] = password
            payload["btn_valida"] = "Iniciar sesión"

            payload.pop("username", None)
            payload.pop("password", None)

            verification_token = payload.get("__RequestVerificationToken")
            print(f"[SSO Log] Token __RequestVerificationToken extraído: {verification_token[:25]}..." if verification_token else "[SSO Warning] Token __RequestVerificationToken no encontrado")

            print(f"[SSO Log] Enviando POST a: {action_url} con campos: {list(payload.keys())}")

            session.headers.update({"Referer": res_init.url})
            res_post = session.post(action_url, data=payload, allow_redirects=True)

            print(f"[SSO Log] Respuesta POST final: {res_post.url}, HTTP Status: {res_post.status_code}")

            parsed_url = urlparse(res_post.url)
            query_params = parse_qs(parsed_url.query)

            is_error_str = query_params.get("is_error", [None])[0] or query_params.get("isError", [None])[0]
            mensaje_error = query_params.get("mensaje_error", [None])[0] or query_params.get("mensajeError", [None])[0] or query_params.get("error", [None])[0]

            is_error = is_error_str is not None and is_error_str.lower() == "true"

            if is_error or mensaje_error:
                error_msg_decoded = unquote(mensaje_error) if mensaje_error else "Error en credenciales del SSO UPAO"
                print(f"[SSO Error Log] Fallo detectado en URL final: {error_msg_decoded}")
                return False, error_msg_decoded, None

            if "studentGrades" in res_post.url or "ssb.upao.edu.pe" in res_post.url:
                print("[SSO Log] Login SSO Exitoso. Sesión autenticada creada en Banner SSB.")
                return True, "Login SSO exitoso sin captcha", session

            if "upaosso" in res_post.url or "Login" in res_post.url:
                return False, "Credenciales o PIN (nip) incorrectos en SSO UPAO", None

            return True, "Login SSO completado con éxito", session

        except Exception as e:
            print(f"[SSO Error] Excepción en flujo SSO: {e}")
            return False, f"Error en conexión SSO: {str(e)}", None

    def get_periodos(self, session: requests.Session) -> dict:
        """
        GET /term?filter=&page=1&max=50 -> Lista de periodos disponibles en Banner SSB.
        Filtra y descarta elementos cuyo 'code' sea igual a '-1' (All Terms).
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
                periodos_clean = []
                items = data if isinstance(data, list) else data.get("items", [])
                
                for item in items:
                    if isinstance(item, dict):
                        code = item.get("code") or item.get("termCode") or item.get("id") or item.get("term")
                        desc = item.get("description") or item.get("termDescription") or item.get("desc") or ""
                        
                        if not code or str(code).strip() == "-1":
                            continue

                        periodos_clean.append({
                            "code": str(code),
                            "description": str(desc),
                            "raw_item": item
                        })

                return {"success": True, "periodos": periodos_clean, "raw": data}

            return {"success": False, "message": f"Error HTTP {res.status_code} al consultar periodos"}
        except Exception as e:
            return {"success": False, "message": f"Excepción en get_periodos: {e}"}

    def get_niveles(self, session: requests.Session, term: str) -> dict:
        """
        GET /level?filter=&term={term} -> Lista de niveles disponibles.
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
                items = data if isinstance(data, list) else data.get("items", [])
                
                for item in items:
                    if isinstance(item, dict):
                        code = item.get("code") or item.get("levelCode") or item.get("id")
                        desc = item.get("description") or item.get("levelDescription") or item.get("desc") or ""
                        
                        if not code or str(code).strip() == "-1":
                            continue

                        niveles_clean.append({
                            "code": str(code),
                            "description": str(desc),
                            "raw_item": item
                        })
                return {"success": True, "niveles": niveles_clean, "raw": data}

            return {"success": False, "message": f"Error HTTP {res.status_code} al consultar niveles"}
        except Exception as e:
            return {"success": False, "message": f"Excepción en get_niveles: {e}"}

    def select_term_context(self, session: requests.Session, term: str) -> bool:
        """
        Establece el periodo activo en la sesión Banner SSB antes de consultar cursos.
        """
        try:
            url = f"{self.ssb_base_url}/selectTerm"
            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": self.ssb_base_url
            })
            res = session.post(url, data={"term": term})
            print(f"[Banner Log] POST selectTerm (term={term}) -> HTTP Status: {res.status_code}")
            return res.status_code == 200
        except Exception as e:
            print(f"[Banner Warning] Error en selectTerm: {e}")
            return False

    def get_courses(self, session: requests.Session, term: str, level: str = "UG") -> dict:
        """
        GET /courses?termCode={term}&levelCode={level}...
        Si con levelCode no devuelve cursos, prueba la consulta directa por termCode para garantizar que ningún curso quede excluido.
        """
        try:
            self.select_term_context(session, term)

            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_base_url
            })

            # Intento 1: Con termCode y levelCode
            url1 = f"{self.ssb_base_url}/courses?termCode={term}&levelCode={level}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
            res1 = session.get(url1)
            print(f"[Banner Log] GET Cursos Intento 1 (Term: {term}, Level: {level}) -> HTTP Status: {res1.status_code}")

            if res1.status_code == 200:
                data1 = res1.json()
                if isinstance(data1, list) and len(data1) > 0:
                    return {"success": True, "totalCount": len(data1), "cursos": data1}

            # Intento 2: Fallback directo solo con termCode (sin restringir por levelCode)
            url2 = f"{self.ssb_base_url}/courses?termCode={term}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
            res2 = session.get(url2)
            print(f"[Banner Log] GET Cursos Intento 2 Fallback (Term: {term}) -> HTTP Status: {res2.status_code}")

            if res2.status_code == 200:
                data2 = res2.json()
                if isinstance(data2, list):
                    return {"success": True, "totalCount": len(data2), "cursos": data2}

            return {"success": True, "totalCount": 0, "cursos": []}
        except Exception as e:
            return {"success": False, "message": f"Excepción en get_courses: {e}"}

    def get_course_grade_detail(self, session: requests.Session, term: str, level: str, crn: str) -> dict:
        """
        Consulta el detalle de notas/componentes de un curso desplegado.
        """
        endpoints = [
            f"{self.ssb_base_url}/components?termCode={term}&levelCode={level}&courseReferenceNumber={crn}",
            f"{self.ssb_base_url}/courseGrades?termCode={term}&levelCode={level}&courseReferenceNumber={crn}",
            f"{self.ssb_base_url}/components?termCode={term}&courseReferenceNumber={crn}"
        ]

        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.ssb_base_url
        })

        for url in endpoints:
            try:
                res = session.get(url)
                if res.status_code == 200:
                    try:
                        data = res.json()
                        return {"success": True, "url_usada": url, "detalles": data}
                    except Exception:
                        pass
            except Exception:
                pass

        return {
            "success": False,
            "status": "PENDIENTE_CONFIRMAR_URL",
            "message": "Arquitectura lista. Pendiente capturar la URL exacta de desgloses vía DevTools.",
            "detalles": []
        }

banner_sso_service = BannerSSOService()
