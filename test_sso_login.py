import sys
import json
from services.banner_sso_service import banner_sso_service

def main():
    print("=== Prueba de Autenticación SSO Ellucian Banner (UPAO) ===")
    if len(sys.argv) < 3:
        print("Uso: python test_sso_login.py <ID_usuario> <contraseña>")
        sys.exit(1)

    user = sys.argv[1]
    password = sys.argv[2]

    print(f"\n1. Ejecutando flujo de inicio de sesión SSO WSO2 para el usuario: {user}...")
    success, message, session = banner_sso_service.login_sso(user, password)

    print(f"\nResultado SSO: success={success}")
    print(f"Mensaje: {message}")

    if success and session is not None:
        print("\n2. Obteniendo cookies de sesión autenticada:")
        for cookie in session.cookies:
            print(f" - {cookie.name}: {cookie.value[:15]}... (Domain: {cookie.domain})")

        print("\n3. Consultando API REST de notas en Banner SSB:")
        grades_result = banner_sso_service.get_student_grades_json(session, term="202610")
        print(f"Respuesta JSON de Notas: {json.dumps(grades_result, indent=2, ensure_ascii=False)}")
    else:
        print("\n[ERROR] El inicio de sesión SSO falló. Revisa las credenciales o los nombres de campos.")

if __name__ == "__main__":
    main()
