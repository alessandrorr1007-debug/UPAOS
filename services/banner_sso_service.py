import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from datetime import date
import json
import re

class BannerSSOService:
    def __init__(self):
        self.ssb_base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"
        self.attendance_base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentAttendanceTracking"
        self.component_base_url = "https://ssb.upao.edu.pe/StudentSelfService/componentDetails"
        self.sso_login_url = "https://upaosso.upao.edu.pe:410/Account/Login"
        self.inscripcion_base_url = "https://inscripcion.upao.edu.pe/StudentRegistrationSsb/ssb"
        self.inscripcion_login_url = "https://inscripcion.upao.edu.pe/StudentRegistrationSsb/login"
        self.inscripcion_registration_history_url = (
            f"{self.inscripcion_base_url}/registrationHistory/registrationHistory"
        )
        self.inscripcion_reset_registrations_url = (
            f"{self.inscripcion_base_url}/registrationHistory/reset"
        )
        self.inscripcion_get_registration_events_url = (
            f"{self.inscripcion_base_url}/classRegistration/getRegistrationEvents"
        )

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

    @staticmethod
    def es_periodo_regular(code) -> bool:
        """
        True si el código de periodo corresponde al ciclo regular de la carrera
        (termina en "10" o "20"). Los códigos que terminan en "90" son Centro de
        Idiomas y NO se consideran ciclo regular.
        """
        s = str(code or "").strip()
        return s.endswith("10") or s.endswith("20")

    @staticmethod
    def periodo_actual(periodos: list) -> str | None:
        """
        Dada la lista devuelta por get_periodos (dicts con 'code'), devuelve el
        periodo regular con el código NUMÉRICO más alto (los códigos son
        cronológicos: 202610 < 202620 < 202710, el más alto es el más reciente).
        Excluye explícitamente los que terminan en "90" (Centro de Idiomas).
        """
        codes = []
        for p in periodos or []:
            code = p.get("code") if isinstance(p, dict) else p
            if not BannerSSOService.es_periodo_regular(code):
                continue
            s = str(code).strip()
            if s.isdigit():
                codes.append(int(s))
        return str(max(codes)) if codes else None

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

    def get_courses_con_notas(self, session: requests.Session, term: str, level: str = "UG") -> dict:
        """
        GET /courses y, para CADA curso, llama internamente a
        get_course_grade_detail() para calcular la NOTA ACTUAL progresiva
        (promedio ponderado de los componentes EP1/Parcial/EP2/Final con nota,
        normalizado por la suma de sus pesos). Devuelve la lista de cursos
        enriquecida con el campo 'nota_actual' (float o None).
        Costo: 1 llamada componentDetails por curso (HTTP directa, sin navegador).
        """
        result = self.get_courses(session, term, level)
        if not result.get("success"):
            return result

        raw_cursos = result.get("cursos", [])
        if isinstance(raw_cursos, dict):
            raw_cursos = raw_cursos.get("data", [])
        if not isinstance(raw_cursos, list):
            raw_cursos = []

        enriquecidos = []
        for item in raw_cursos:
            if not isinstance(item, dict):
                continue
            curso = dict(item)
            crn = (
                item.get("courseReferenceNumber")
                or item.get("crn")
                or item.get("id")
                or item.get("sectionMeetingId")
            )
            if crn:
                detail = self.get_course_grade_detail(session, term, str(crn))
                componentes = self._extraer_componentes_con_peso(detail)
                curso["nota_actual"] = self._calcular_nota_actual(componentes)
            enriquecidos.append(curso)

        print(f"[Banner Log] Cursos enriquecidos con nota_actual: {len(enriquecidos)}")
        return {
            "success": True,
            "totalCount": len(enriquecidos),
            "cursos": enriquecidos,
        }

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
    def _peso_componente(componente: dict) -> float | None:
        """
        Peso oficial del componente según el sistema UPAO:
        EP1=20, Parcial=30, EP2=20, Final=30.
        Devuelve None si el componente no corresponde a una evaluación ponderada.
        """
        texto = " ".join(
            str(componente.get(k) or "") for k in ("description", "nombre", "codigo", "componente")
        ).upper()
        if "FINAL" in texto or "EVF" in texto:
            return 30.0
        if "PARCIAL" in texto or "EVP" in texto:
            return 30.0
        if "EP2" in texto or "PROCESO 2" in texto:
            return 20.0
        if "EP1" in texto or "PROCESO 1" in texto:
            return 20.0
        return None

    @staticmethod
    def _extraer_componentes_con_peso(detail_result: dict) -> list:
        """
        Devuelve los componentes ponderados (EP1, Parcial, EP2, Final) que YA
        tienen nota registrada, como [{'nota': float, 'peso': float}, ...].
        """
        componentes = []
        for c in detail_result.get("detalles", []):
            if not isinstance(c, dict):
                continue
            peso = BannerSSOService._peso_componente(c)
            if peso is None:
                continue
            nota = BannerSSOService._parse_float(c.get("puntaje_obtenido"))
            if nota is None:
                continue
            componentes.append({"nota": nota, "peso": peso})
        return componentes

    @staticmethod
    def _calcular_nota_actual(componentes_con_peso: list) -> float | None:
        """
        Promedio ponderado progresivo: usa SOLO los componentes con nota y
        normaliza por la suma de sus pesos (peso relativo entre lo disponible).
        Ej: EP1=15 y Parcial=14 -> (15*20 + 14*30) / (20+30) = 14.4
        Devuelve None si ningún componente tiene nota.
        """
        suma_ponderada = 0.0
        suma_pesos = 0.0
        for c in componentes_con_peso:
            suma_ponderada += c["nota"] * c["peso"]
            suma_pesos += c["peso"]
        if suma_pesos <= 0:
            return None
        return round(suma_ponderada / suma_pesos, 2)

    @staticmethod
    def _calcular_promedio_general(cursos: list) -> tuple:
        """
        Promedio simple de las notas actuales (nota_actual) disponibles por curso.
        Devuelve (promedio, base) con base 'nota_actual', o None si no hay notas.
        Nunca devuelve 0 falso.
        """
        notas = []
        for c in cursos:
            nota = BannerSSOService._parse_float(c.get("nota_actual"))
            if nota is not None:
                notas.append(nota)
        if notas:
            return round(sum(notas) / len(notas), 2), "nota_actual"
        return None, None

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

    def _preparar_sesion_inscripcion(self, session: requests.Session) -> None:
        """
        getRegistrationEvents vive en inscripcion.upao.edu.pe (subdominio distinto
        al de notas/asistencia). La primera visita a ese subdominio dispara un
        intercambio SSO automático vía login.upao.edu.pe (cookies compartidas del
        WSO2) que otorga cookies propias al subdominio. Sin este GET previo, la
        llamada de eventos se "consume" devolviendo el JSON del intercambio en vez
        de la lista.
        """
        if session is None:
            return
        tiene_cookie_inscripcion = any(
            c.domain and "inscripcion.upao.edu.pe" in c.domain
            for c in session.cookies
        )
        if not tiene_cookie_inscripcion:
            print("[Banner Log] Intercambio SSO hacia inscripcion.upao.edu.pe (1 GET).")
            try:
                session.get(self.inscripcion_login_url, timeout=20, allow_redirects=True)
            except Exception as e:
                print(f"[Banner Warning] Intercambio SSO inscripcion falló: {e}")

    @staticmethod
    def _parse_fecha_horario(iso_str) -> tuple | None:
        """
        '2026-08-03T07:00:27-0500' -> (dia_semana, 'HH:MM') con Lunes=0.
        El endpoint devuelve fechas que son solo una plantilla de 'la semana
        actual'; lo único significativo es el día de la semana y la hora.
        """
        if not isinstance(iso_str, str):
            return None
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", iso_str)
        if not m:
            return None
        year, month, day, hh, mm = (int(x) for x in m.groups())
        try:
            weekday = date(year, month, day).weekday()
        except ValueError:
            return None
        return weekday, f"{hh:02d}:{mm:02d}"

    @staticmethod
    def _a_12h(hhmm: str | None) -> str | None:
        """'07:00' -> '7:00 AM'. None si no es una hora válida."""
        if not hhmm or ":" not in hhmm:
            return None
        try:
            hh, mm = hhmm.split(":")
            h = int(hh)
            h12 = h % 12 or 12
            suf = "AM" if h < 12 else "PM"
            return f"{h12}:{mm} {suf}"
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fusionar_bloques(bloques: list) -> list:
        """
        Une bloques consecutivos del mismo día (fin == inicio del siguiente)
        en un solo rango, p. ej. dos eventos de una misma clase de 2 horas
        continuas se muestran como un único bloque 07:00-10:00.
        """
        if not bloques:
            return []
        por_dia: dict[int, list] = {}
        for b in bloques:
            por_dia.setdefault(b["dia"], []).append(b)

        result = []
        for dia, lista in por_dia.items():
            lista.sort(key=lambda b: b["hora_inicio"])
            merged = [dict(lista[0])]
            for b in lista[1:]:
                ultimo = merged[-1]
                if b["hora_inicio"] == ultimo.get("hora_fin"):
                    ultimo["hora_fin"] = b["hora_fin"]
                    ultimo["hora_fin_12h"] = b["hora_fin_12h"]
                else:
                    merged.append(dict(b))
            result.extend(merged)
        return result

    def _agrupar_horario(self, eventos: list, term: str) -> list:
        """
        Agrupa los eventos crudos de getRegistrationEvents por curso (crn) y por
        día de la semana. Devuelve una estructura simple para el frontend:
        [{crn, codigo_materia, numero_curso, nombre, bloques:[{dia, dia_nombre,
        hora_inicio, hora_fin, hora_inicio_12h, hora_fin_12h}]}]
        """
        dias_nombres = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
        cursos: dict[str, dict] = {}
        for ev in eventos:
            if not isinstance(ev, dict):
                continue
            crn = ev.get("crn") or ev.get("courseReferenceNumber") or ev.get("id")
            if crn is None:
                continue
            inicio = self._parse_fecha_horario(ev.get("start"))
            if inicio is None:
                continue
            fin = self._parse_fecha_horario(ev.get("end"))
            dia, hora_inicio = inicio
            hora_fin = fin[1] if fin else None

            clave = str(crn)
            curso = cursos.get(clave)
            if curso is None:
                curso = {
                    "crn": clave,
                    "codigo_materia": ev.get("subject"),
                    "numero_curso": ev.get("courseNumber"),
                    "nombre": ev.get("title") or ev.get("courseTitle") or "Curso",
                    "bloques": [],
                }
                cursos[clave] = curso
            curso["bloques"].append({
                "dia": dia,
                "dia_nombre": dias_nombres[dia] if 0 <= dia < 7 else str(dia),
                "hora_inicio": hora_inicio,
                "hora_fin": hora_fin,
                "hora_inicio_12h": self._a_12h(hora_inicio),
                "hora_fin_12h": self._a_12h(hora_fin),
                "aula": self._aula_de_meeting(ev) or ev.get("location"),
            })

        result = []
        for crn, curso in cursos.items():
            curso["bloques"] = sorted(
                self._fusionar_bloques(curso["bloques"]),
                key=lambda b: (b["dia"], b["hora_inicio"]),
            )
            result.append(curso)
        result.sort(key=lambda c: (c["nombre"] or "").lower())
        return result

    @staticmethod
    def _hora_hhmm_a_formato(hhmm) -> str | None:
        """'1950' -> '19:50'. None si no es un HHMM válido."""
        if not isinstance(hhmm, str) or len(hhmm) != 4 or not hhmm.isdigit():
            return None
        return f"{hhmm[:2]}:{hhmm[2:]}"

    @staticmethod
    def _desescapar_html(valor):
        """'Aplicaciones M&oacute;viles...' -> 'Aplicaciones Móviles...'."""
        if not isinstance(valor, str):
            return valor
        from html import unescape
        return unescape(valor)

    @staticmethod
    def _aula_de_meeting(mt: dict) -> str | None:
        """'buildingDescription' + 'room' -> 'PABELLÓN G G701'. None si no hay aula."""
        from html import unescape
        room = mt.get("room")
        building = mt.get("buildingDescription")
        partes = [unescape(str(p)).strip() for p in (building, room) if p]
        return unescape(" ".join(partes)) if partes else None

    def _agrupar_horario_desde_registros(self, registros: list, term: str) -> list:
        """
        Construye la estructura de horario a partir de data.registrations de
        registrationHistory/reset (página 'View Registration Information' →
        tab Lookup Schedule). El endpoint devuelve una fila por CRN registrado
        (teoría/práctica van como CRNs distintos del mismo curso), cada una con
        meetingTimes (beginTime/endTime en 'HHMM' y flags por día). Se agrupa por
        curso (subject + courseNumber) fusionando todas sus secciones, y por día,
        fusionando bloques consecutivos del mismo día.
        """
        dias_nombres = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
        flag_dias = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        cursos: dict[str, dict] = {}
        for reg in registros:
            if not isinstance(reg, dict):
                continue
            crn = reg.get("courseReferenceNumber") or reg.get("crn")
            subject = reg.get("subject")
            numero = reg.get("courseNumber")
            if crn is None and subject is None:
                continue
            if subject is not None and numero is not None:
                clave = f"{subject}|{numero}"
            else:
                clave = f"crn:{crn}"
            curso = cursos.get(clave)
            if curso is None:
                curso = {
                    "crn": str(crn) if crn is not None else clave,
                    "codigo_materia": subject,
                    "numero_curso": numero,
                    "nombre": self._desescapar_html(reg.get("courseTitle")) or "Curso",
                    "bloques": [],
                }
                cursos[clave] = curso
            for mt in reg.get("meetingTimes") or []:
                if not isinstance(mt, dict):
                    continue
                inicio = self._hora_hhmm_a_formato(mt.get("beginTime"))
                fin = self._hora_hhmm_a_formato(mt.get("endTime"))
                if inicio is None:
                    continue
                for idx, flag in enumerate(flag_dias):
                    if mt.get(flag):
                        curso["bloques"].append({
                            "dia": idx,
                            "dia_nombre": dias_nombres[idx],
                            "hora_inicio": inicio,
                            "hora_fin": fin,
                            "hora_inicio_12h": self._a_12h(inicio),
                            "hora_fin_12h": self._a_12h(fin),
                            "aula": self._aula_de_meeting(mt),
                        })
                        break

        result = []
        for crn, curso in cursos.items():
            curso["bloques"] = sorted(
                self._fusionar_bloques(curso["bloques"]),
                key=lambda b: (b["dia"], b["hora_inicio"] or ""),
            )
            result.append(curso)
        result.sort(key=lambda c: (c["nombre"] or "").lower())
        return result

    def get_horario(self, session: requests.Session, term: str) -> dict:
        """
        Horario semanal de inscripcion.upao.edu.pe (Banner Student Registration),
        página 'View Registration Information' → endpoint registrationHistory/reset
        (tab Lookup Schedule). Reutiliza la sesión SSO de Banner; el subdominio
        distinto se resuelve solo con el intercambio SSO automático (1 GET al login
        del subdominio). El endpoint devuelve las inscripciones reales del periodo
        (una fila por CRN registrado, con meetingTimes: día + hora inicio/fin) y
        filtra correctamente por term. Si no hay registros, se intenta el
        calendario getRegistrationEvents (requiere que el periodo esté activo en
        la sesión).
        """
        try:
            self._preparar_sesion_inscripcion(session)

            session.headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.inscripcion_registration_history_url,
            })
            session.get(self.inscripcion_registration_history_url, timeout=20, allow_redirects=True)

            res = session.get(
                self.inscripcion_reset_registrations_url,
                params={"term": term},
                timeout=20,
                allow_redirects=True,
            )
            print(f"[Banner Log] GET registrationHistory/reset (term={term}) -> HTTP Status: {res.status_code}")

            registros = []
            if res.status_code == 200:
                try:
                    data = res.json()
                except (ValueError, TypeError):
                    data = None
                if isinstance(data, dict):
                    registros = data.get("data", {}).get("registrations", [])
                    if not isinstance(registros, list):
                        registros = []

            if not registros:
                print(f"[Banner Log] Sin registros vía reset; intentando getRegistrationEvents.")
                res = session.get(
                    self.inscripcion_get_registration_events_url,
                    params={"termFilter": term},
                    timeout=20,
                    allow_redirects=True,
                )
                print(f"[Banner Log] GET getRegistrationEvents (term={term}) -> HTTP Status: {res.status_code}")
                eventos = []
                if res.status_code == 200:
                    try:
                        data = res.json()
                    except (ValueError, TypeError):
                        data = None
                    if isinstance(data, list):
                        eventos = data
                cursos = self._agrupar_horario(eventos, term)
            else:
                cursos = self._agrupar_horario_desde_registros(registros, term)

            print(f"[Banner Log] Horario OK: {len(cursos)} cursos, "
                  f"{sum(len(c['bloques']) for c in cursos)} bloques.")
            return {
                "success": True,
                "periodo": term,
                "total_cursos": len(cursos),
                "total_bloques": sum(len(c["bloques"]) for c in cursos),
                "cursos": cursos,
            }
        except Exception as e:
            print(f"[Banner Error] Excepción en get_horario: {e}")
            return {
                "success": False,
                "status": "EXCEPCION",
                "message": f"Excepción en get_horario: {e}",
                "cursos": [],
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

    def scrape_horario_creditos(self, session: requests.Session, periodo: str) -> list:
        """
        Scrapea la página/endpoint de Horario/Cursos para extraer por cada curso:
        - CRN (courseReferenceNumber)
        - Nombre del curso (courseTitle)
        - Créditos (creditHours)
        Devuelve lista de dicts: [{'crn': str, 'nombre': str, 'creditos': int|float}, ...]
        """
        creditos_lista = []
        try:
            courses_res = self.get_courses(session, periodo)
            if courses_res.get("success"):
                cursos_raw = courses_res.get("cursos", [])
                if isinstance(cursos_raw, dict):
                    cursos_raw = cursos_raw.get("data", [])
                if isinstance(cursos_raw, list):
                    for item in cursos_raw:
                        if not isinstance(item, dict):
                            continue
                        crn = str(item.get("courseReferenceNumber") or item.get("crn") or item.get("id") or "").strip()
                        nombre = str(item.get("courseTitle") or item.get("subjectDescription") or item.get("nombre") or "").strip()
                        creditos_val = (
                            item.get("creditHours")
                            or item.get("creditHourLow")
                            or item.get("credits")
                            or item.get("creditHourHigh")
                            or item.get("hoursAttempted")
                            or item.get("hoursEarned")
                            or item.get("gpaHours")
                        )
                        creditos_num = None
                        if creditos_val is not None:
                            try:
                                creditos_num = int(float(str(creditos_val).strip()))
                            except (ValueError, TypeError):
                                creditos_num = None
                        
                        if crn or nombre:
                            creditos_lista.append({
                                "crn": crn,
                                "nombre": nombre,
                                "creditos": creditos_num
                            })
        except Exception as e:
            print(f"[Banner Warning] Excepción scraping créditos en Horario: {e}")

        print(f"[Banner Log] Créditos extraídos para periodo {periodo}: {len(creditos_lista)} cursos.")
        return creditos_lista

    @staticmethod
    def combinar_notas_creditos(notas: list, horario_creditos: list) -> list:
        """
        Combina la lista de cursos con notas y la lista de horario por CRN (o nombre como fallback).
        Si un CRN no aparece o no tiene créditos, loguea un warning y asigna creditos = None sin fallar.
        """
        mapa_crn = {}
        mapa_nombre = {}
        for h in horario_creditos or []:
            if not isinstance(h, dict):
                continue
            crn = str(h.get("crn") or "").strip()
            nombre = str(h.get("nombre") or "").strip().lower()
            cred = h.get("creditos")
            if crn:
                mapa_crn[crn] = cred
            if nombre:
                mapa_nombre[nombre] = cred

        resultado = []
        for n in notas or []:
            if not isinstance(n, dict):
                continue
            curso_copy = dict(n)
            crn = str(n.get("crn") or n.get("courseReferenceNumber") or "").strip()
            nombre = str(n.get("nombre") or n.get("courseTitle") or "").strip().lower()

            creditos = mapa_crn.get(crn)
            if creditos is None and nombre:
                creditos = mapa_nombre.get(nombre)

            if creditos is None:
                print(f"[PPS Warning] No se encontraron créditos para curso CRN '{crn}' / '{n.get('nombre')}'. Asignado None.")

            curso_copy["creditos"] = creditos
            resultado.append(curso_copy)

        return resultado

    @staticmethod
    def calcular_pps(cursos: list) -> float | None:
        """
        Cálculo del Promedio Ponderado Semestral (PPS):
        PPS = Σ(nota * creditos) / Σ(creditos)
        Si algún curso no tiene créditos o nota válida (None), se excluye y advierte.
        Conserva precisión decimal.
        """
        cursos_validos = []
        for c in cursos or []:
            if not isinstance(c, dict):
                continue
            nota_val = c.get("nota") if c.get("nota") is not None else c.get("nota_actual")
            cred_val = c.get("creditos")
            if nota_val is not None and cred_val is not None:
                try:
                    n_float = float(nota_val)
                    c_float = float(cred_val)
                    if c_float > 0:
                        cursos_validos.append((n_float, c_float))
                except (ValueError, TypeError):
                    continue
            else:
                print(f"[PPS Warning] Curso excluido de PPS por faltar nota/créditos: {c.get('nombre')}")

        if not cursos_validos:
            return None

        suma_ponderada = sum(nota * cred for nota, cred in cursos_validos)
        total_creditos = sum(cred for _, cred in cursos_validos)
        if total_creditos <= 0:
            return None

        return round(suma_ponderada / total_creditos, 4)

    def obtener_promedio_periodo(self, session: requests.Session, periodo: str, cursos: list = None) -> dict:
        """
        Obtiene el resumen de promedio del periodo (PPS oficial vs calculado).
        1. Intenta obtener el pps_oficial directamente del portal (Cuadro de Mérito si existe).
        2. Scrapea los créditos del periodo y combina con las notas para pps_calculado.
        """
        pps_oficial = None
        fuente = "calculado"

        try:
            url_merito = f"{self.ssb_base_url}/studentMerit?term={periodo}"
            res_m = session.get(url_merito, timeout=5)
            if res_m.status_code == 200:
                data = res_m.json() if "json" in res_m.headers.get("Content-Type", "") else {}
                if isinstance(data, dict) and data.get("pps"):
                    pps_oficial = float(data["pps"])
                    fuente = "cuadro_merito"
        except Exception:
            pass

        if cursos is None:
            courses_res = self.get_courses_con_notas(session, periodo)
            cursos = courses_res.get("cursos", [])

        horario_creditos = self.scrape_horario_creditos(session, periodo)
        cursos_combinados = self.combinar_notas_creditos(cursos, horario_creditos)
        pps_calculado = self.calcular_pps(cursos_combinados)

        total_creditos = sum(c.get("creditos") for c in cursos_combinados if c.get("creditos") is not None)

        return {
            "success": True,
            "periodo": periodo,
            "pps_oficial": pps_oficial,
            "pps_calculado": pps_calculado,
            "fuente": fuente if pps_oficial else "calculado",
            "total_creditos": total_creditos if total_creditos > 0 else None,
            "cursos": [
                {
                    "crn": str(c.get("courseReferenceNumber") or c.get("crn") or c.get("id") or ""),
                    "nombre": c.get("courseTitle") or c.get("subjectDescription") or c.get("nombre") or "",
                    "nota": c.get("nota_actual") if c.get("nota_actual") is not None else c.get("nota"),
                    "creditos": c.get("creditos")
                }
                for c in cursos_combinados
            ]
        }

banner_sso_service = BannerSSOService()
