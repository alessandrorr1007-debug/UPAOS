import sys
import json
from services.banner_sso_service import banner_sso_service

def main():
    print("=== Inspección de Respuesta Cruda JSON de Banner SSB (UPAO) ===")
    if len(sys.argv) < 3:
        print("Uso: python test_sso_login.py <ID_usuario> <contraseña>")
        sys.exit(1)

    user = sys.argv[1]
    password = sys.argv[2]

    print(f"\n1. Ejecutando inicio de sesión SSO WSO2 para usuario: {user}...")
    success, message, session = banner_sso_service.login_sso(user, password)

    print(f"Resultado Login SSO: success={success}")
    print(f"Mensaje del servidor: {message}")

    if success and session is not None:
        print("\n2. Consultando lista de Periodos Académicos (GET /term)...")
        periodos_res = banner_sso_service.get_periodos(session)
        raw_data = periodos_res.get("raw", [])
        
        print("\n==================== [LISTA COMPLETA DE PERIODOS RECIBIDOS SIN FILTRAR] ====================")
        print(json.dumps(raw_data, indent=2, ensure_ascii=False))
        print("=============================================================================================\n")

        periodos_list = periodos_res.get("periodos", [])
        print(f"Periodos Parseados: {json.dumps(periodos_list, indent=2, ensure_ascii=False)}")

        if not periodos_list:
            print("[Warning] No se encontraron elementos en la respuesta.")
            return

        # Buscar el primer periodo donde code no sea vacio / null
        real_period = None
        for p in periodos_list:
            code = p.get("code")
            desc = p.get("description", "")
            if code and "todos los periodos" not in desc.lower():
                real_period = p
                break

        if not real_period:
            real_period = periodos_list[0]

        selected_term = real_period.get("code")
        term_desc = real_period.get("description")
        print(f"\n3. Seleccionado Periodo para Consulta: {term_desc} (Código: {selected_term})")

        print(f"\n4. Consultando Niveles para el periodo {selected_term} (GET /level)...")
        niveles_res = banner_sso_service.get_niveles(session, selected_term)
        niveles_list = niveles_res.get("niveles", [])
        selected_level = niveles_list[0].get("code") if niveles_list else "UB"
        level_desc = niveles_list[0].get("description") if niveles_list else "PREGRADO"
        print(f"\n5. Seleccionado Nivel: {level_desc} (Código: {selected_level})")

        print(f"\n6. Consultando Lista de Cursos (GET /courses?termCode={selected_term}&levelCode={selected_level})...")
        courses_res = banner_sso_service.get_courses(session, selected_term, selected_level)
        print(f"\n=== RESULTADO FINAL DE CURSOS (Total: {courses_res.get('totalCount')}) ===")
        print(json.dumps(courses_res, indent=2, ensure_ascii=False))

    else:
        print("\n[FALLO] El inicio de sesión SSO falló.")

if __name__ == "__main__":
    main()
