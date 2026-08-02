import sys
import json
from services.banner_sso_service import banner_sso_service

def test_terms(user, password):
    success, msg, session = banner_sso_service.login_sso(user, password)
    if not success:
        print("Login SSO falló.")
        return

    base_url = "https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades"

    # 1. Periodos disponibles
    res_terms = session.get(f"{base_url}/term?filter=&page=1&max=50")
    print("GET /term status:", res_terms.status_code)
    terms_list = res_terms.json()
    print("Terms:", [t.get("code") for t in terms_list])

    for term in ["202520", "202510", "202610", "202690"]:
        print(f"\n==================== [PROBANDO TERM {term}] ====================")
        
        # Probar POST a selectTerm
        r_sel1 = session.post(f"{base_url}/selectTerm", data={"term": term})
        print(f"POST selectTerm (term={term}): Status {r_sel1.status_code}, URL: {r_sel1.url}")

        # Probar GET a selectTerm
        r_sel2 = session.get(f"{base_url}/selectTerm?term={term}")
        print(f"GET selectTerm?term={term}: Status {r_sel2.status_code}")

        # Probar GET a setTerm
        r_sel3 = session.get(f"{base_url}/setTerm?term={term}")
        print(f"GET setTerm?term={term}: Status {r_sel3.status_code}")

        # Probar GET a courses
        url_courses = f"{base_url}/courses?termCode={term}&levelCode=UG&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
        res_c = session.get(url_courses)
        print(f"GET /courses status: {res_c.status_code}")
        if res_c.status_code == 200:
            c_json = res_c.json()
            data_list = c_json.get("data", []) if isinstance(c_json, dict) else (c_json if isinstance(c_json, list) else [])
            print(f"Cursos encontrados para {term}: {len(data_list)}")
            if len(data_list) > 0:
                print("PRIMER CURSO:", json.dumps(data_list[0], indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_terms(sys.argv[1], sys.argv[2])
