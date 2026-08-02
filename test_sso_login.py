import sys
import json
import time
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
        
        print(f"Periodos Reales Obtenidos (Sin '-1'): {json.dumps(periodos_list, indent=2, ensure_ascii=False)}")

        if not periodos_list:
            print("[Warning] No se encontraron periodos válidos.")
            return

        # Buscar explícitamente el periodo 2026-I (código '202610' o primer periodo válido de la lista)
        selected_term_obj = next((p for p in periodos_list if p.get("code") == "202610"), periodos_list[0])
        selected_term = selected_term_obj.get("code")
        term_desc = selected_term_obj.get("description")
        print(f"\n3. Seleccionado Periodo Académico Real: {term_desc} (Código: {selected_term})")

        print(f"\n4. Consultando Niveles para el periodo {selected_term} (GET /level)...")
        niveles_res = banner_sso_service.get_niveles(session, selected_term)
        niveles_list = niveles_res.get("niveles", [])
        print(f"Niveles Obtenidos (Sin '-1'): {json.dumps(niveles_list, indent=2, ensure_ascii=False)}")

        # Seleccionar explícitamente el nivel 'UG' (PREGRADO)
        selected_level_obj = next((n for n in niveles_list if n.get("code") == "UG"), niveles_list[0] if niveles_list else {"code": "UG", "description": "PREGRADO"})
        selected_level = selected_level_obj.get("code")
        level_desc = selected_level_obj.get("description")
        print(f"\n5. Seleccionado Nivel Oficial: {level_desc} (Código: {selected_level})")

        print(f"\n6. Consultando Lista de Cursos enriquecida con PARCIAL/FINAL reales (GET /courses + componentDetails por curso)...")
        t0 = time.time()
        courses_res = banner_sso_service.get_courses_con_notas(session, selected_term, selected_level)
        t1 = time.time()
        print(f"Tiempo total (cursos + {courses_res.get('totalCount')} llamadas componentDetails): {t1 - t0:.2f}s")
        print(f"\n=== RESULTADO DE CURSOS ENRIQUECIDOS DEL PERIODO {selected_term} / NIVEL {selected_level} (Total: {courses_res.get('totalCount')}) ===")
        print(json.dumps(courses_res, indent=2, ensure_ascii=False))

        cursos = courses_res.get("cursos", [])
        resumen = [
            {
                "nombre": (c.get("courseTitle") or c.get("subjectDescription") or c.get("courseNumber") or "Curso"),
                "crn": (c.get("courseReferenceNumber") or c.get("crn") or c.get("id")),
                "nota_actual": c.get("nota_actual"),
            }
            for c in cursos if isinstance(c, dict)
        ]
        print(f"\n=== RESUMEN NOTA ACTUAL POR CURSO ===")
        print(json.dumps(resumen, indent=2, ensure_ascii=False))

        promedio_general, promedio_basado_en = banner_sso_service._calcular_promedio_general(cursos)
        print(f"\n=== PROMEDIO GENERAL: {promedio_general} (basado en: {promedio_basado_en}) ===")

        selected_course = next(
            (c for c in cursos if isinstance(c, dict) and str(c.get("hasComponent", "")).upper() == "Y"),
            None
        )
        if selected_course is None and cursos:
            selected_course = next((c for c in cursos if isinstance(c, dict)), None)

        print(f"\n7. Consultando desglose por componentes (GET componentDetails) del primer curso con hasComponent='Y'...")
        if selected_course is None:
            print("[Warning] No se encontraron cursos para consultar el desglose.")
            return

        detail_crn = selected_course.get("courseReferenceNumber") or selected_course.get("crn") or selected_course.get("id")
        print(f"Curso seleccionado: {selected_course.get('courseTitle')} (CRN: {detail_crn})")
        detail_res = banner_sso_service.get_course_grade_detail(session, selected_term, str(detail_crn))
        print(f"\n=== RESULTADO DE DESGLOSE DE COMPONENTES (termCode={selected_term}, CRN={detail_crn}) ===")
        print(json.dumps(detail_res, indent=2, ensure_ascii=False))

        print(f"\n8. Consultando Asistencia (GET getRegisteredSections, pageMaxSize=50)...")
        attendance_res = banner_sso_service.get_attendance(session)
        print(f"\n=== RESULTADO DE ASISTENCIA (Total: {attendance_res.get('totalCount')}, raw_totalCount: {attendance_res.get('raw_totalCount')}) ===")
        print(json.dumps(attendance_res, indent=2, ensure_ascii=False))

    else:
        print("\n[FALLO] El inicio de sesión SSO falló. Verifique credenciales.")

if __name__ == "__main__":
    main()
