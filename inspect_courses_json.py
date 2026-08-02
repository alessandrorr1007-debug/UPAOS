import sys
import json
from services.banner_sso_service import banner_sso_service

def main():
    user = sys.argv[1]
    password = sys.argv[2]

    success, msg, session = banner_sso_service.login_sso(user, password)
    if not success:
        print("Login SSO falló.")
        return

    # Probar periodos 202690, 202610, 202520
    for term in ["202690", "202610", "202520"]:
        url = f"https://ssb.upao.edu.pe/StudentSelfService/ssb/studentGrades/courses?termCode={term}&filterText=&pageOffset=0&pageMaxSize=50&sortColumn=-1&sortDirection=-1"
        res = session.get(url)
        print(f"\n==================== [RAW /courses PARA TERM {term}] ====================")
        print(f"Status Code: {res.status_code}")
        try:
            val = res.json()
            print(f"Tipo de dato Python: {type(val)}")
            if isinstance(val, dict):
                print(f"Keys del diccionario: {list(val.keys())}")
                for k, v in val.items():
                    if isinstance(v, list):
                        print(f" - Key '{k}' es lista de tamaño: {len(v)}")
                        if len(v) > 0:
                            print(f"   Primer elemento de '{k}': {json.dumps(v[0], indent=2, ensure_ascii=False)}")
            elif isinstance(val, list):
                print(f"Es una lista de tamaño: {len(val)}")
                if len(val) > 0:
                    print(f"   Primer elemento de la lista: {json.dumps(val[0], indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"Error parsing JSON: {e}")

if __name__ == "__main__":
    main()
