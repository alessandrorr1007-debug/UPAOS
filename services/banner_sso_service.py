import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import json

class BannerSSOService:
    def __init__(self):
        self.ssb_base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        self.attendance_base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentAttendanceTracking"
        self.component_base_url = "https://ssb.upao.edu.pe/StudentSelfService/componentDetails"
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

    def get_courses(self, session: requests.Session, term: str, level: str = "UG") -> dict:
        """
        GET /courses?termCode={term}&levelCode={level}...
        Si con levelCode devuelve 0 cursos, automáticamente realiza el fallback a la búsqueda por termCode directo.
        """
        try:
            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.ssb_base_url
            })

            # URL 1: Con termCode y levelCode
            url1 = f"{self.ssb_base_url}/courses?termCode={term}&levelCode={level}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
            print(f"[Banner Diagnostic] Solicitando UPAO URL (Intento 1): {url1}")
            res1 = session.get(url1)
            print(f"[Banner Diagnostic] UPAO HTTP Status: {res1.status_code}")

            course_list = []
            json_body1 = None

            if res1.status_code == 200:
                json_body1 = res1.json()
                print(f"[Banner Diagnostic] UPAO JSON completo recibido (Intento 1):\n{json.dumps(json_body1, indent=2, ensure_ascii=False)}")
                
                if isinstance(json_body1, dict):
                    course_list = json_body1.get("data", [])
                elif isinstance(json_body1, list):
                    course_list = json_body1

            # Si con levelCode se obtienen 0 cursos, ejecutar Fallback sin levelCode
            if len(course_list) == 0:
                url2 = f"{self.ssb_base_url}/courses?termCode={term}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
                print(f"[Banner Diagnostic] 0 Cursos obtenidos con level '{level}'. Ejecutando Fallback (Intento 2): {url2}")
                res2 = session.get(url2)
                print(f"[Banner Diagnostic] Fallback UPAO HTTP Status: {res2.status_code}")

                if res2.status_code == 200:
                    json_body2 = res2.json()
                    print(f"[Banner Diagnostic] UPAO JSON completo recibido (Fallback):\n{json.dumps(json_body2, indent=2, ensure_ascii=False)}")
                    if isinstance(json_body2, dict):
                        course_list = json_body2.get("data", [])
                    elif isinstance(json_body2, list):
                        course_list = json_body2

            print(f"[Banner Diagnostic] TOTAL CURSOS EXTRAÍDOS para term={term}: {len(course_list)} elementos.")
            return {
                "success": True,
                "totalCount": len(course_list),
                "cursos": course_list,
                "raw_response": json_body1
            }

        except Exception as e:
            print(f"[Banner Error] Excepción en get_courses: {e}")
            return {"success": False, "message": f"Excepción en get_courses: {e}"}

    @staticmethod
    def _extraer_valor(item: dict, keys) -> object:
        """Devuelve el primer valor no None entre las claves candidatas."""
        for key in keys:
            value = item.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _parse_float(val) -> float | None:
        """Convierte a float conservando decimales; None si no es numérico."""
        if val is None:
            return None
        try:
            s = str(val).strip()
            if s in ("", "null", "None", "-"):
                return None
            return float(s)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _es_componente_final(componente: dict) -> bool:
        """Detecta el componente de evaluación final (EVF / 'EVALUACION FINAL')."""
        for clave in ("description", "nombre", "codigo", "componente"):
            val = componente.get(clave)
            if val:
                txt = str(val).upper()
                if "FINAL" in txt or "EVF" in txt:
                    return True
        return False

    @staticmethod
    def _calcular_nota_proyectada(componentes: list) -> dict:
        """
        Calcula una nota proyectada (estimación no oficial) cuando el componente
        Final (EVF) está pendiente pero los demás componentes con peso > 0 sí
        tienen nota. Nunca modifica el grade oficial de Banner; devuelve campos
        separados: nota_proyectada, pesos_pendientes y nota_proyectada_info.
        Si el Final ya tiene nota (o no hay suficientes datos), no devuelve nada.
        """
        comp_final = next((c for c in componentes if BannerSSOService._es_componente_final(c)), None)
        if comp_final is None or BannerSSOService._parse_float(comp_final.get("puntaje_obtenido")) is not None:
            return {}

        suma_ponderada = 0.0
        pesos_pendientes = []
        componentes_con_nota = 0
        for c in componentes:
            peso = BannerSSOService._parse_float(c.get("peso"))
            nota = BannerSSOService._parse_float(c.get("puntaje_obtenido"))
            if peso is None or peso <= 0:
                continue
            if nota is None:
                pesos_pendientes.append(c.get("nombre") or c.get("codigo") or c.get("description") or "Componente")
                continue
            suma_ponderada += nota * (peso / 100.0)
            componentes_con_nota += 1

        if componentes_con_nota == 0:
            return {}

        # 2 decimales para evitar artefactos de coma flotante.
        return {
            "nota_proyectada": round(suma_ponderada, 2),
            "pesos_pendientes": pesos_pendientes,
            "nota_proyectada_info": (
                "Estimación no oficial basada en los pesos de los componentes con nota registrada."
            )
        }

    @staticmethod
    def _convertir_horario(schedule) -> str:
        """Convierte el array schedule [Lun..Dom] ('false' o letra del día) a texto legible."""
        dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        activos = []
        if isinstance(schedule, list):
            for idx, val in enumerate(schedule):
                if idx < len(dias) and val not in (None, "", "false", "False", False):
                    activos.append(dias[idx])
        return ", ".join(activos) if activos else "Sin horario registrado"

    @staticmethod
    def _convertir_hora(hora_raw):
        """Convierte '1420' a ('14:20', '2:20 PM'). Devuelve el valor original si no es válido."""
        try:
            s = str(hora_raw).strip()
            if len(s) == 4 and s.isdigit():
                hh = int(s[:2])
                mm = s[2:]
                suffix = "AM" if hh < 12 else "PM"
                h12 = hh % 12
                if h12 == 0:
                    h12 = 12
                return f"{s[:2]}:{mm}", f"{h12}:{mm} {suffix}"
        except (TypeError, ValueError):
            pass
        return hora_raw, hora_raw

    @staticmethod
    def _normalizar_asistencia(item: dict) -> dict:
        """Mapea un item real de getRegisteredSections a nombres en español."""
        crn = item.get("courseReferenceNumber")
        course_number = item.get("courseNumber") or item.get("courseDisplayValue")
        term = item.get("termCode")
        subject_desc = item.get("subjectDesc")
        subject_code = item.get("subjectCode")
        section_title = item.get("sectionTitle")
        sequence = item.get("sequenceNumber")
        hora_24, hora_12 = BannerSSOService._convertir_hora(item.get("time"))

        return {
            "crn": str(crn) if crn is not None else None,
            "curso": str(course_number) if course_number is not None else None,
            "materia": subject_desc,
            "codigo_materia": subject_code,
            "nombre_curso": section_title,
            "seccion": str(sequence) if sequence is not None else None,
            "periodo": str(term) if term is not None else None,
            "faltas": item.get("missed"),
            "porcentaje": item.get("percentage"),
            "horario_dias": BannerSSOService._convertir_horario(item.get("schedule")),
            "hora": hora_24,
            "hora_12h": hora_12,
            "sectionMeetingId": item.get("sectionMeetingId"),
            "sub_periodo": item.get("partOfTermCode"),
            "raw": item
        }

    def get_attendance(self, session: requests.Session, page_max_size: int = 50) -> dict:
        """
        GET getRegisteredSections (API JSON directa de Banner, reutiliza la sesión
        SSO autenticada). Trae TODOS los cursos con asistencia de TODOS los periodos
        en una única llamada (pageMaxSize=50). Si el total real supera pageMaxSize,
        pagina automáticamente con pageOffset hasta reunir totalCount.
        """
        url_template = (
            f"{self.attendance_base_url}/getRegisteredSections?filterText="
            f"&pageMaxSize={page_max_size}&pageOffset={{offset}}"
            f"&sortColumn=courseReferenceNumber&sortDirection=asc"
        )
        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.attendance_base_url
        })

        all_items = []
        total_count = None
        offset = 0
        try:
            while True:
                url = url_template.format(offset=offset)
                print(f"[Banner Diagnostic] GET getRegisteredSections (pageOffset={offset}): {url}")
                res = session.get(url, timeout=15)
                print(f"[Banner Log] GET getRegisteredSections -> HTTP Status: {res.status_code}")
                if res.status_code != 200:
                    return {
                        "success": False,
                        "status": f"HTTP_{res.status_code}",
                        "message": f"Error HTTP {res.status_code} al consultar asistencia",
                        "asistencia": []
                    }

                data = res.json()
                items = data.get("data", []) if isinstance(data, dict) else []
                raw_total = data.get("totalCount") if isinstance(data, dict) else None
                if raw_total is not None:
                    total_count = raw_total

                all_items.extend(items)

                # Paginación real: seguir hasta juntar todos los registros.
                if len(items) == 0:
                    break
                if total_count is not None and len(all_items) >= int(total_count):
                    break
                if offset > 10000:
                    print("[Banner Warning] Límite de seguridad de paginación alcanzado en get_attendance.")
                    break
                offset += page_max_size

            asistencia = [
                self._normalizar_asistencia(item)
                for item in all_items if isinstance(item, dict)
            ]
            print(f"[Banner Log] getRegisteredSections OK: {len(asistencia)} registros de asistencia.")
            return {
                "success": True,
                "totalCount": len(asistencia),
                "raw_totalCount": total_count,
                "asistencia": asistencia
            }
        except Exception as e:
            print(f"[Banner Error] Excepción en get_attendance: {e}")
            return {
                "success": False,
                "status": "EXCEPCION",
                "message": f"Excepción en get_attendance: {e}",
                "asistencia": []
            }

    def _normalizar_componente(self, item: dict) -> dict:
        """
        Normaliza un item real de componentDetails/subComponentDetails
        (net.hedtech.banner.student.ComponentDetailsDecorator).
        """
        component_id = self._extraer_valor(item, ["componentId", "componentID", "id"])
        nombre = str(self._extraer_valor(item, [
            "description", "componentDescription", "name", "componentName", "title"
        ]) or "Componente")
        codigo = self._extraer_valor(item, ["name", "componentName", "componentCode"])
        peso = self._extraer_valor(item, ["weight", "weightPercent", "percentWeight", "gradeWeight"])
        porcentaje_logrado = self._extraer_valor(item, ["percentage", "percentAchieved"])
        # Banner envía "grade" (nota oficial, normalmente redondeada a entero, ej. "11")
        # y "score" (valor exacto con decimales, ej. "10.7"). Se muestra el "score"
        # exacto tal cual; solo si el grade es cualitativo (ej. "APR") se usa el grade.
        grade_val = self._extraer_valor(item, [
            "grade", "gradeEarned", "midtermGrade", "finalGrade", "calculatedFinalGrade"
        ])
        score_val = self._extraer_valor(item, ["score", "pointsEarned", "earnedPoints"])
        if grade_val is not None and self._parse_float(grade_val) is None:
            obtenido = grade_val
        else:
            obtenido = score_val if score_val is not None else grade_val
        score_raw = score_val
        sobre = self._extraer_valor(item, [
            "totalScore", "possible", "maxPoints", "totalPoints", "pointPossible", "maxScore"
        ])
        has_sub_raw = self._extraer_valor(item, [
            "hasSubComponents", "hasSubcomponents", "hasSubComponent", "hasComponents", "hasChildren"
        ])
        sub_count = self._extraer_valor(item, ["subComponentCount"])

        has_sub_bool = bool(has_sub_raw) and str(has_sub_raw).upper() not in ("N", "0", "FALSE", "NO", "NONE")
        try:
            if int(sub_count or 0) > 0:
                has_sub_bool = True
        except (TypeError, ValueError):
            pass

        return {
            "nombre": nombre,
            "codigo": str(codigo) if codigo is not None else None,
            "peso": peso,
            "porcentaje_logrado": porcentaje_logrado,
            "puntaje_obtenido": obtenido,
            "puntaje_sobre": sobre,
            "score": score_raw,
            "grade_oficial": grade_val,
            "componentId": component_id,
            "hasSubComponents": has_sub_bool,
            "subcomponentes": [],
            # Aliases de compatibilidad con la app Android (GradesScreen.kt)
            "description": nombre,
            "grade": obtenido,
            "componente": nombre,
            "nota": obtenido,
            "raw": item
        }

    def get_subcomponent_details(self, session: requests.Session, term: str, crn: str, component_id) -> dict:
        """
        GET subComponentDetails (API JSON directa de Banner, confirmada con DevTools):
        https://ssb.upao.edu.pe/StudentSelfService/componentDetails/subComponentDetails
        Devuelve los sub-componentes de un componente (ej. dentro de EP1:
        'CL - Control de Laboratorio').
        """
        url = (
            f"{self.component_base_url}/subComponentDetails?selectedTerm={term}"
            f"&selectedCrn={crn}&selectedComponentId={component_id}"
            f"&filterText=&pageOffset=0&pageMaxSize=20&sortColumn=name&sortDirection=asc"
        )
        print(f"[Banner Diagnostic] GET subComponentDetails: {url}")

        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.component_base_url}/componentDetails"
        })

        try:
            res = session.get(url, timeout=15)
            print(f"[Banner Log] GET subComponentDetails -> HTTP Status: {res.status_code}")
            if res.status_code == 200:
                data = res.json()
                items = data.get("data", []) if isinstance(data, dict) else data
                if isinstance(items, list):
                    subcomponentes = [
                        self._normalizar_componente(item)
                        for item in items if isinstance(item, dict)
                    ]
                    return {"success": True, "subcomponentes": subcomponentes, "raw": data}
                return {"success": False, "status": "FORMATO_INESPERADO", "subcomponentes": []}
            return {
                "success": False,
                "status": f"HTTP_{res.status_code}",
                "message": f"Error HTTP {res.status_code} en subComponentDetails",
                "subcomponentes": []
            }
        except Exception as e:
            print(f"[Banner Error] Excepción en get_subcomponent_details: {e}")
            return {
                "success": False,
                "status": "EXCEPCION",
                "message": f"Excepción en get_subcomponent_details: {e}",
                "subcomponentes": []
            }

    def get_course_grade_detail(self, session: requests.Session, term: str, crn: str) -> dict:
        """
        GET componentDetails (API JSON directa de Banner, 1 sola llamada HTTP):
        https://ssb.upao.edu.pe/StudentSelfService/componentDetails/componentDetails
        Reutiliza la sesión ya autenticada (cookies). Sin Playwright ni navegador.
        Para cada componente con hasSubComponents, hace 1 GET adicional a
        subComponentDetails (2 llamadas HTTP en total).
        """
        url = (
            f"{self.component_base_url}/componentDetails?selectedTerm={term}"
            f"&selectedCrn={crn}&filterText=&pageOffset=0&pageMaxSize=20"
            f"&sortColumn=name&sortDirection=asc"
        )
        print(f"[Banner Diagnostic] GET componentDetails: {url}")

        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.component_base_url}/componentDetails"
        })

        try:
            res = session.get(url, timeout=15)
            print(f"[Banner Log] GET componentDetails -> HTTP Status: {res.status_code}")
            if res.status_code != 200:
                return {
                    "success": False,
                    "status": f"HTTP_{res.status_code}",
                    "message": f"Error HTTP {res.status_code} al consultar componentDetails",
                    "detalles": []
                }

            data = res.json()
            items = data.get("data", []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                return {
                    "success": False,
                    "status": "FORMATO_INESPERADO",
                    "message": "La respuesta de componentDetails no contiene la lista 'data'.",
                    "raw": data,
                    "detalles": []
                }

            componentes = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                comp = self._normalizar_componente(item)

                if comp["hasSubComponents"]:
                    sub_res = self.get_subcomponent_details(
                        session, term, crn, comp["componentId"]
                    )
                    comp["subcomponentes"] = sub_res.get("subcomponentes", [])

                componentes.append(comp)

            print(f"[Banner Log] componentDetails OK: {len(componentes)} componentes para CRN {crn}.")
            result = {
                "success": True,
                "totalCount": len(componentes),
                "detalles": componentes
            }
            result.update(self._calcular_nota_proyectada(componentes))
            return result
        except Exception as e:
            print(f"[Banner Error] Excepción en get_course_grade_detail: {e}")
            return {
                "success": False,
                "status": "EXCEPCION",
                "message": f"Excepción en get_course_grade_detail: {e}",
                "detalles": []
            }

banner_sso_service = BannerSSOService()
