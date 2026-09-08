import sys
import json
import requests
from services.scraper_service import scraper_service, ACTIVE_SESSIONS
from services.banner_sso_service import banner_sso_service


def test_meeting_info(usuario, password, term="202610", crn=None):
    print(f"=== 1. Login SSO para {usuario} ===")
    result = scraper_service.login(usuario, password)
    if not result.get("success"):
        print("Error en login:", result)
        return

    session = ACTIVE_SESSIONS.get(result["token"])
    if not session:
        print("No se encontró sesión activa.")
        return

    print("=== 2. Preparar sesión en inscripcion.upao.edu.pe ===")
    banner_sso_service._preparar_sesion_inscripcion(session)

    # 3. Si no pasaron CRN, obtener lista de CRNs vía reset
    if not crn:
        print(f"=== 3. Obteniendo CRNs disponibles para periodo {term} ===")
        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": banner_sso_service.inscripcion_registration_history_url,
        })
        res_reset = session.get(
            banner_sso_service.inscripcion_reset_registrations_url,
            params={"term": term},
            timeout=25
        )
        if res_reset.status_code == 200:
            try:
                data = res_reset.json()
                registros = data.get("data", {}).get("registrations", [])
                if registros:
                    print(f"Encontrados {len(registros)} registros de inscripción.")
                    crns = [r.get("courseReferenceNumber") for r in registros if r.get("courseReferenceNumber")]
                    print("CRNs disponibles:", crns)
                    crn = crns[0]
                    # También imprimimos un registro completo de reset para comparar
                    print("\n--- MUESTRA REGISTRO REGISTRATIONHISTORY/RESET ---")
                    print(json.dumps(registros[0], indent=2, ensure_ascii=False)[:2000])
            except Exception as e:
                print("Error parseando reset:", e)

    if not crn:
        print("No se pudo obtener un CRN de prueba.")
        return

    print(f"\n=== 4. Probando getMeetingInformationForRegistrations con CRN={crn}, Term={term} ===")
    base_meeting_url = f"{banner_sso_service.inscripcion_base_url}/classRegistration/getMeetingInformationForRegistrations"
    
    session.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{banner_sso_service.inscripcion_base_url}/classRegistration/classRegistration",
    })

    # Probar GET con diferentes combinaciones de params
    variantes = [
        {"name": "GET con term y courseReferenceNumber", "method": "GET", "params": {"term": term, "courseReferenceNumber": crn}},
        {"name": "GET con termFilter y crn", "method": "GET", "params": {"termFilter": term, "crn": crn}},
        {"name": "GET con term y crn", "method": "GET", "params": {"term": term, "crn": crn}},
        {"name": "POST con term y courseReferenceNumber", "method": "POST", "data": {"term": term, "courseReferenceNumber": crn}},
        {"name": "GET sin params (bulk)", "method": "GET", "params": {}},
        {"name": "GET solo con term", "method": "GET", "params": {"term": term}},
    ]

    for v in variantes:
        print(f"\n---> Probando {v['name']} -> URL: {base_meeting_url}")
        try:
            if v["method"] == "GET":
                r = session.get(base_meeting_url, params=v.get("params"), timeout=15)
            else:
                r = session.post(base_meeting_url, data=v.get("data"), timeout=15)
            
            print(f"Status: {r.status_code} | Content-Type: {r.headers.get('content-type')}")
            print(f"Response (primeros 1500 caracteres):\n{r.text[:1500]}")
            if r.status_code == 200:
                try:
                    j = r.json()
                    print("\n=== RAW JSON COMPLETO ===")
                    print(json.dumps(j, indent=2, ensure_ascii=False))
                    # Si respondió con datos válidos, guardamos en archivo para Step 1
                    with open("step1_raw_meeting_info.json", "w", encoding="utf-8") as f:
                        json.dump(j, f, indent=2, ensure_ascii=False)
                    print("\n[ÉXITO] Guardado en step1_raw_meeting_info.json")
                    break
                except Exception:
                    pass
        except Exception as e:
            print(f"Excepción: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python test_meeting_info.py <usuario> <password> [term] [crn]")
        sys.exit(1)
    user = sys.argv[1]
    pwd = sys.argv[2]
    t = sys.argv[3] if len(sys.argv) > 3 else "202610"
    c = sys.argv[4] if len(sys.argv) > 4 else None
    test_meeting_info(user, pwd, t, c)
