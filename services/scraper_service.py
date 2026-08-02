import base64
import requests
from bs4 import BeautifulSoup
from config import settings
from services.ocr_service import process_captcha_ocr

ACTIVE_SESSIONS: dict[str, requests.Session] = {}

class CampusScraperService:
    def __init__(self):
        self.login_url = settings.CAMPUS_URL
        self.captcha_url = settings.CAPTCHA_URL
        self.notas_url = settings.NOTAS_URL

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
        
        # Petición al captcha agregando el header Referer correcto
        captcha_res = session.get(
            self.captcha_url,
            headers={"Referer": self.login_url}
        )
        captcha_bytes = captcha_res.content
        content_type = captcha_res.headers.get("Content-Type", "")
        
        print(f"[Backend Log] GET Captcha -> HTTP Status: {captcha_res.status_code}")
        print(f"[Backend Log] GET Captcha -> Content-Type: {content_type}")
        print(f"[Backend Log] GET Captcha -> Tamaño de bytes: {len(captcha_bytes)}")

        # Guardar en archivo local temporal para depuración visual directa
        debug_filename = "debug_captcha.png" if "image" in content_type.lower() else "debug_captcha.html"
        try:
            with open(debug_filename, "wb") as f:
                f.write(captcha_bytes)
            print(f"[Backend Log] Archivo local de depuración guardado en: {debug_filename}")
        except Exception as e:
            print(f"[Backend Warning] No se pudo guardar {debug_filename}: {e}")

        if "image" not in content_type.lower():
            print(f"[Backend CRÍTICO] La URL del captcha devolvió {content_type} en vez de imagen! Primeros 200 caracteres:\n{captcha_bytes[:200].decode('utf-8', errors='ignore')}")

        return session, form_data, captcha_bytes

    def login(self, username: str, password: str, manual_captcha: str | None = None) -> dict:
        session, form_fields, captcha_bytes = self.initialize_login_session()
        
        captcha_code = manual_captcha
        if not captcha_code:
            captcha_code = process_captcha_ocr(captcha_bytes)
            
        if not captcha_code:
            img_b64 = base64.b64encode(captcha_bytes).decode("utf-8")
            print(f"[Backend Log] OCR falló. Retornando fallback base64 con {len(captcha_bytes)} bytes de imagen (String Base64: {len(img_b64)} chars).")
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
                "message": "Login exitoso"
            }
        else:
            # Re-solicitar un captcha FRESCO para el nuevo intento si el POST falló
            try:
                fresh_captcha = session.get(self.captcha_url, headers={"Referer": self.login_url}).content
                fresh_b64 = base64.b64encode(fresh_captcha).decode("utf-8")
                print(f"[Backend Log] POST Login rechazado. Obtenida nueva imagen fresca ({len(fresh_captcha)} bytes). String Base64: {len(fresh_b64)} chars.")
            except Exception:
                fresh_b64 = base64.b64encode(captcha_bytes).decode("utf-8")

            return {
                "success": False,
                "necesita_captcha": True,
                "imagen_base64": fresh_b64,
                "message": "Código o credenciales incorrectos."
            }

    def get_notas(self, token: str, periodo: str, carrera: str) -> dict:
        session = ACTIVE_SESSIONS.get(token)
        if not session:
            return {"error": "Sesión no encontrada o expirada. Vuelva a iniciar sesión."}

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
                        "nota": float(ep1_val) if ep1_val.isdigit() else ep1_val,
                        "detalles": []
                    },
                    "parcial": float(parcial_val) if parcial_val.isdigit() else parcial_val,
                    "ep2": {
                        "nota": float(ep2_val) if ep2_val.isdigit() else ep2_val,
                        "detalles": []
                    },
                    "final": float(final_val) if final_val.isdigit() else final_val
                })

        return {
            "periodo": periodo,
            "carrera": carrera,
            "cursos": cursos
        }

scraper_service = CampusScraperService()
