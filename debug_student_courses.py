import sys
import json
from services.banner_sso_service import banner_sso_service

def debug_student(user, password):
    print(f"=== DEPURACIÓN DE CURSOS PARA ESTUDIANTE: {user} ===")
    success, message, session = banner_sso_service.login_sso(user, password)
    print(f"Login SSO: success={success}, msg={message}")
    
    if not success or session is None:
        print("Login falló.")
        return

    print("\n1. Obteniendo periodos reales de Banner SSB (GET /term)...")
    periodos_res = banner_sso_service.get_periodos(session)
    raw_periodos = periodos_res.get("periodos", [])
    print(f"Periodos encontrados ({len(raw_periodos)}):")
    for p in raw_periodos:
        print(f" - Código: '{p.get('code')}' -> Descripción: '{p.get('description')}'")

    if not raw_periodos:
        print("No se devolvieron periodos.")
        return

    for p in raw_periodos:
        term_code = p.get("code")
        term_desc = p.get("description")
        print(f"\n--- PROBANDO PERIODO: {term_desc} (Código: {term_code}) ---")
        
        # Consultar niveles para este periodo
        niveles_res = banner_sso_service.get_niveles(session, term_code)
        raw_niveles = niveles_res.get("niveles", [])
        print(f"Niveles para {term_code}: {[n.get('code') for n in raw_niveles]}")
        
        level_to_test = raw_niveles[0].get("code") if raw_niveles else "UG"
        
        # Consultar cursos con level
        res_courses = banner_sso_service.get_courses(session, term_code, level_to_test)
        cursos = res_courses.get("cursos", [])
        print(f"Cursos con level '{level_to_test}': {len(cursos)} encontrados.")
        
        if not cursos:
            # Probar sin level parameter
            url_no_level = f"https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades/courses?termCode={term_code}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
            r = session.get(url_no_level)
            if r.status_code == 200:
                c_no_level = r.json()
                print(f"Cursos SIN level (solo termCode={term_code}): {len(c_no_level)} encontrados.")
                if c_no_level:
                    print("Muestra de cursos:", [c.get("courseTitle") or c.get("subjectDescription") for c in c_no_level[:3]])

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        debug_student(sys.argv[1], sys.argv[2])
    else:
        print("Uso: python debug_student_courses.py <usuario> <contraseña>")
