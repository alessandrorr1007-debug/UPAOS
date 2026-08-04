import sys
import json
from services.scraper_service import scraper_service, ACTIVE_SESSIONS
from services.banner_sso_service import banner_sso_service


def main():
    if len(sys.argv) < 3:
        print("Uso: python test_horario_e2e.py <ID_usuario> <contrasena> [term]")
        sys.exit(1)
    usuario, password = sys.argv[1], sys.argv[2]
    term = sys.argv[3] if len(sys.argv) >= 4 else "202610"

    print(f"=== 1. Login SSO (upaosso.upao.edu.pe / Banner SSB) para {usuario} ===")
    result = scraper_service.login(usuario, password)
    print("Login:", {k: v for k, v in result.items() if k != "session"})
    if not result.get("success"):
        print("FALLO el login. No se puede continuar.")
        sys.exit(2)
    session = ACTIVE_SESSIONS.get(result["token"])
    if session is None:
        print("No hay sesión en ACTIVE_SESSIONS.")
        sys.exit(2)

    print(f"\n=== 2. Intercambio SSO hacia inscripcion.upao.edu.pe ===")
    banner_sso_service._preparar_sesion_inscripcion(session)
    cookies_inscripcion = [
        (c.name, c.domain) for c in session.cookies if c.domain and "inscripcion" in c.domain
    ]
    print("Cookies para inscripcion:", cookies_inscripcion)

    print(f"\n=== 3. Llamada RAW a registrationHistory/reset (fuente real del horario) ===")
    url = banner_sso_service.inscripcion_reset_registrations_url
    session.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": banner_sso_service.inscripcion_registration_history_url,
    })
    res = session.get(url, params={"term": term}, timeout=25, allow_redirects=True)
    print(f"HTTP {res.status_code} | URL final: {res.url} | Content-Type: {res.headers.get('content-type')}")
    if res.status_code != 200:
        print(f"Body (primeros 800):\n{res.text[:800]}")
        sys.exit(0)

    try:
        data = res.json()
    except Exception as e:
        print(f"No es JSON válido: {e}. Primeros 800 chars:\n{res.text[:800]}")
        sys.exit(0)

    registros = data.get("data", {}).get("registrations", []) if isinstance(data, dict) else []
    print(f"data.registrations: {len(registros)} cursos")
    if registros:
        print("Claves del primer registro:", list(registros[0].keys()))
        print("Ejemplo primer meetingTime:",
              json.dumps(registros[0].get("meetingTimes", [{}])[0], ensure_ascii=False)[:900])

    print(f"\n=== 4. get_horario parseado (agrupado por curso/día) ===")
    parsed = banner_sso_service.get_horario(session, term)
    print(json.dumps({k: v for k, v in parsed.items() if k != "cursos"}, ensure_ascii=False, indent=2))
    for c in parsed.get("cursos", []):
        print(f"- {c['nombre']} [{c.get('codigo_materia')} {c.get('numero_curso')}] (CRN {c['crn']})")
        for b in c["bloques"]:
            print(f"    {b['dia_nombre']} {b.get('hora_inicio_12h') or b.get('hora_inicio')} - "
                  f"{b.get('hora_fin_12h') or b.get('hora_fin')}")

    print(f"\n=== 5. registrationHistory/reset en varios periodos ===")
    for t in ["202610", "202510", "202410"]:
        try:
            r = session.get(url, params={"term": t}, timeout=15)
            body = r.json()
            n = len(body.get("data", {}).get("registrations", [])) if isinstance(body, dict) else None
            print(f"  term={t} -> {r.status_code} | "
                  f"{'registros ' + str(n) if n is not None else 'respuesta: ' + str(body)[:100]}")
        except Exception as e:
            print(f"  term={t} -> ERROR: {e}")


if __name__ == "__main__":
    main()
