# UPAOS Backend — API de Servicios Universitarios UPAO

Backend en **FastAPI** diseñado para conectar y sincronizar los servicios académicos de la **Universidad Privada Antenor Orrego (UPAO)** mediante integración directa con los portales institucionales y el sistema **Ellucian Banner 9 Self-Service (SSB)**.

---

## 🚀 Características Principales

- **Autenticación SSO Integrada:** Conexión vía OAuth2/OIDC con el proveedor WSO2 de UPAO (`upaosso.upao.edu.pe`) para sesiones en Banner SSB sin necesidad de resolver CAPTCHA.
- **Horario Semanal (`/horario`):** Extracción y normalización de inscripciones y horarios de clase desde Banner Student Registration (`inscripcion.upao.edu.pe`), con agrupación inteligente de bloques de teoría, práctica y laboratorio.
- **Calificaciones en Vivo (`/notas`):** Consulta de periodos académicos, cursos y desglose de notas oficiales por componentes (EP1, EP2, parcial, final y subcomponentes).
- **Control de Asistencia (`/asistencia`):** Seguimiento del registro de asistencias, inasistencias y porcentaje de faltas por curso.
- **Cálculo de Promedio Ponderado Semestral (PPS):** Ponderación automática basada en créditos académicos y notas oficiales.
- **Panel Administrativo (`/admin`):** Métricas de uso activo (DAU), gestión de cuentas, configuración de semanas del ciclo y buzón de sugerencias.
- **Seguridad:** Cifrado simétrico de credenciales almacenadas mediante Fernet y autenticación basada en tokens de sesión.

---

## 🛠️ Tecnologías Utilizadas

- **Lenguaje:** Python 3.10+
- **Framework Web:** [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/)
- **Scraping / Conexión:** [Requests](https://requests.readthedocs.io/), [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)
- **Base de Datos & ORM:** SQLite / PostgreSQL vía [SQLAlchemy](https://www.sqlalchemy.org/)
- **Criptografía & Hashing:** Cryptography (Fernet), Bcrypt
- **Contenedorización & Deploy:** Docker, Render (`render.yaml`)

---

## 📁 Estructura del Proyecto

```text
├── services/
│   ├── banner_sso_service.py   # Cliente y extractor de datos de Banner SSB (SSO, notas, horario, asistencia)
│   ├── scraper_service.py      # Gestor de sesiones activas y autenticación híbrida
│   ├── features_service.py     # Lógica de panel admin, métricas, sugerencias y semanas
│   └── ocr_service.py          # Soporte OCR opcional para CAPTCHA de portales legados
├── main.py                     # Definición de rutas y endpoints de la API FastAPI
├── database.py                 # Modelos SQLAlchemy y configuración de sesión de BD
├── config.py                   # Variables de entorno y configuración general
├── Dockerfile                  # Empaquetado para despliegue en contenedor
├── render.yaml                 # Manifiesto de despliegue en Render
├── requirements.txt            # Dependencias del proyecto
├── CHECKLIST.md                # Documentación técnica interna y estados de endpoints
└── tests/
    ├── smoke_features_test.py  # Pruebas de integración de features y admin
    ├── test_admin_auth.py      # Validación de roles y permisos admin
    ├── test_horario_e2e.py     # Prueba de extracción de horario en vivo
    └── test_sso_login.py       # Prueba de autenticación contra SSO UPAO
```

---

## ⚙️ Instalación y Configuración Local

### 1. Clonar el repositorio
```bash
git clone https://github.com/alessandrorr1007-debug/UPAOS.git
cd UPAOS
```

### 2. Crear y activar entorno virtual
```bash
# Con uv (recomendado)
uv venv venv
venv\Scripts\activate

# O con python estándar
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Variables de Entorno
Copia el archivo `.env.example` a `.env` y define las variables requeridas:
```bash
cp .env.example .env
```

Variables disponibles:
- `SECRET_KEY`: Clave para firma de tokens o sesiones.
- `FERNET_KEY`: Clave válida de 32 bytes en base64 para el cifrado seguro de credenciales.
- `DATABASE_URL`: URI de la base de datos (por defecto `sqlite:///./upaos.db`).
- `PORT`: Puerto de escucha del servicio (por defecto `8000`).

---

## 🚦 Ejecución del Servidor

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Una vez levantado, puedes acceder a la documentación interactiva Swagger en:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **Healthcheck:** `http://localhost:8000/healthz`

---

## 📡 Endpoints Principales

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/login` | Inicia sesión con credenciales UPAO o administrador |
| `GET` | `/notas/periodos` | Lista los periodos académicos disponibles |
| `GET` | `/notas` | Consulta notas de cursos del periodo seleccionado |
| `GET` | `/horario` | Obtiene el horario de clases agrupado por días y bloques |
| `GET` | `/asistencia` | Obtiene el reporte y porcentaje de asistencia por curso |
| `GET` | `/ranking/pps` | Consulta o calcula el promedio ponderado semestral |
| `GET` | `/admin/metricas` | Métricas de uso de la plataforma (DAU / actividad) |
| `GET` | `/admin/cuentas` | Listado administrativo de cuentas registradas |

---

## 🧪 Pruebas

Para ejecutar las pruebas de validación técnica:

```bash
# Pruebas de autenticación y panel admin
python test_admin_auth.py

# Pruebas de humo de características
python smoke_features_test.py

# Prueba E2E de horario (requiere credenciales reales)
python test_horario_e2e.py <usuario> <contraseña> [term]
```

---

## 🚢 Despliegue en Producción

El proyecto está configurado para desplegarse de manera continua en [Render](https://render.com) mediante `render.yaml`. Cualquier cambio en la rama `master` dispara la construcción y actualización automática del servicio en producción.
