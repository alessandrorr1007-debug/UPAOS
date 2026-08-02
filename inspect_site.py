import urllib.request
import urllib.parse
import http.cookiejar
import re

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36')]

try:
    print("--- 1. Pidiendo login.aspx ---")
    res = opener.open('https://campusvirtual.upao.edu.pe/login.aspx')
    print("Status:", res.status)
    html = res.read().decode('utf-8', errors='ignore')
    print("HTML Length:", len(html))

    cookies = list(cj)
    print("Cookies obtenidas:", [c.name for c in cookies])

    # Buscar campos de formulario
    inputs = re.findall(r'<input[^>]+name=[\"\']([^\"\']+)[\"\'][^>]*value=[\"\']([^\"\']*)[\"\']', html, re.IGNORECASE)
    print("Campos Input encontrados:", inputs[:5])

    # Buscar imagen de captcha
    imgs = re.findall(r'<img[^>]+>', html, re.IGNORECASE)
    print("Etiquetas <img> encontradas:", imgs)

    captcha_srcs = [i for i in imgs if 'captcha' in i.lower()]
    print("Imágenes de Captcha:", captcha_srcs)

    # Probar petición a captcha.ashx usando la misma sesión
    print("\n--- 2. Pidiendo captcha.ashx ---")
    captcha_url = 'https://campusvirtual.upao.edu.pe/captcha.ashx'
    req = urllib.request.Request(captcha_url, headers={'Referer': 'https://campusvirtual.upao.edu.pe/login.aspx'})
    c_res = opener.open(req)
    print("Captcha HTTP Status:", c_res.status)
    content_type = c_res.headers.get('Content-Type')
    print("Captcha Content-Type:", content_type)
    c_bytes = c_res.read()
    print("Captcha Tamaño Bytes:", len(c_bytes))

    with open("debug_captcha_test.png", "wb") as f:
        f.write(c_bytes)
    print("Guardado debug_captcha_test.png localmente.")

except Exception as e:
    print("Error:", e)
