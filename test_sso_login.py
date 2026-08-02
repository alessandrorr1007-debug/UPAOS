import sys
import json
from services.banner_sso_service import banner_sso_service

def main():
    print("=== Prueba de Autenticación y Extracción Real Ellucian Banner SSB (UPAO) ===")
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
        print("\n2. Consultando lista de Periodos Académicos reales (GET /term)...")
        periodos_res = banner_sso_service.get_periodos(session)
        periodos_list = periodos_res.get("periodos", [])
        
        print(f"Periodos Reales Obtenidos (Filtrados): {json.dumps(periodos_list, indent=2, ensure_ascii=False)}")

        if not periodos_list:
            print("[Warning] No se encontraron periodos válidos con código.")
            return

        # Seleccionar el primer periodo académico real (ej. code="202690" -> 2026-I)
        selected_term = periodos_list[0].get("code")
        term_desc = periodos_list[0].get("description")
        print(f"\n3. Seleccionado Periodo Académico Real: {term_desc} (Código: {selected_term})")

        print(f"\n4. Consultando Niveles/Carreras para el periodo {selected_term} (GET /level)...")
        niveles_res = banner_sso_service.get_niveles(session, selected_term)
        niveles_list = niveles_res.get("niveles", [])
        print(f"Niveles Obtenidos: {json.dumps(niveles_list, indent=2, ensure_ascii=False)}")

        selected_level = niveles_list[0].get("code") if niveles_list else "UB"
        level_desc = niveles_list[0].get("description") if niveles_list else "PREGRADO"
        print(f"\n5. Seleccionado Nivel: {level_desc} (Código: {selected_level})")

        print(f"\n6. Consultando Lista de Cursos (GET /courses?termCode={selected_term}&levelCode={selected_level})...")
        courses_res = banner_sso_service.get_courses(session, selected_term, selected_level)
        print(f"\n=== RESULTADO FINAL DE CURSOS ===")
        print(json.dumps(courses_res, indent=2, ensure_ascii=False))

        print("\n[Nota técnica] El objeto /courses trae metadata de cursos con 'hasComponent': 'Y'. El endpoint específico para obtener las notas desglosadas por componente queda listo para conectar tan pronto se obtenga su URL vía DevTools.")

    else:
        print("\n[FALLO] El inicio de sesión SSO falló. Verifique las credenciales o los parámetros retornados.")

if __name__ == "__main__":
    main()
