# UPAOS Backend — Checklist Técnico

## Horario de clases (`/horario`)

### Dónde vive
- El horario **NO** está en `campusvirtual.upao.edu.pe` ni en `ssb.upao.edu.pe/StudentSelfService`.
- Vive en **inscripcion.upao.edu.pe** → Ellucian **Banner Student Registration** (mismo SSB que notas, pero otro subdominio).

### Autenticación
- No es un login independiente: se **reutiliza la sesión SSO WSO2** ya obtenida con `login_sso()` (upsosso → `ssb.upao.edu.pe`). El `.../login?TARGET=...` visto en Network es parte del flujo de redirección del SSO (tipo CAS/OIDC), **no** un formulario WebForms aparte.
- El subdominio distinto se resuelve **solo**: la primera petición a `inscripcion.upao.edu.pe` dispara un **intercambio SSO automático** vía `login.upao.edu.pe/commonauth` (cookies compartidas) que entrega cookies propias al subdominio (`_preparar_sesion_inscripcion`).
- **CAPTCHA (`captcha.ashx`) es exclusivo del portal de notas** en `campusvirtual.upao.edu.pe`. Este subsistema NO usa captcha.
- Sin el GET de intercambio previo, las llamadas AJAX al subdominio se "consumen" devolviendo el JSON del intercambio (`{"success": true, "username": ...}`) en lugar de datos reales.

### Fuente de datos (confirmada empíricamente)
- **Endpoint definitivo** (página "View Registration Information" → tab Lookup Schedule):
  - `GET https://inscripcion.upao.edu.pe/StudentRegistrationSsb/ssb/registrationHistory/reset?term=202610`
  - El frontend lo llama por **GET** con `term` en query param (Backbone collection fetch). **POST** con `term` en body también funciona (verificado: misma respuesta). Se usa GET para replicar el tráfico del navegador.
  - Devuelve `data.registrations`: **una fila por CRN registrado** (teoría/práctica de un mismo curso son CRNs distintos), cada una con:
    - `subject`, `courseNumber`, `courseTitle` (HTML-escaped, p. ej. `M&oacute;viles`), `courseReferenceNumber` (CRN), `term`, `statusDescription` ("Inscrito"), `scheduleDescription` ("TEOR&Iacute;A" / "PR&Aacute;CTICA" — HTML-escaped, para distinguir teoría/laboratorio/práctica), `grade` (nota del curso, puede ser `null`), `instructorNames[]`, `faculty[]`.
    - `meetingTimes[]`: `beginTime`/`endTime` en **formato `HHMM`** (p. ej. `"1950"` = 19:50), flags `monday..sunday` (booleanos), `room`, `buildingDescription`, `meetingTypeDescription`, `startDate`/`endDate`, `term`.
  - **Filtra correctamente por periodo** (probado: 13 registros en 202610, 14 en 202510, 16 en 202410).
- Flujo mínimo: `login_sso()` → `_preparar_sesion_inscripcion()` (1 GET al login del subdominio) → `GET registrationHistory/registrationHistory` (warm-up) → `GET reset?term={term}` → parsear.
- **Notas del ciclo actual**: este mismo endpoint incluye `grade` por curso. Está documentado como fuente potencial para Notas del ciclo actual, pero el scraping de notas (históricas, campusvirtual.upao.edu.pe) NO se toca — es funcional y usa otro portal.

### Formato de salida del backend (`get_horario`)
- Se agrupa por **curso** (`subject` + `courseNumber`), fusionando las secciones (CRNs) del mismo curso y los bloques consecutivos del mismo día.
- Bloques: `{dia (0-6, LUN=0), dia_nombre (LUN..DOM), hora_inicio, hora_fin, hora_inicio_12h, hora_fin_12h, aula}`. `hora_*` en `HH:MM`; `hora_*_12h` en `h:mm AM/PM`. `aula` = `buildingDescription + room` de `meetingTimes` (p. ej. `AULAS A 201`).
- Ejemplo real verificado (2026-I): `HUMA 1185 METODOLOGIA DE LA INVESTIGACION CIENTIFICA` → Sáb 14:20-16:05 y Sáb 16:10-17:55 (coincide con el evento `getRegistrationEvents` visto en DevTools: CRN 3233, Sáb 2026-08-08 14:20-16:05).

### Endpoints descartados (para no volver a investigar)
- `classRegistration/getRegistrationEvents?termFilter=` → devuelve eventos de calendario **solo si el periodo está "activo" en la sesión** (requiere el flujo de elegibilidad). En sesión nueva devuelve `[]` siempre. Se deja como fallback.
- `term/termSelection` + `POST term/saveTerm` + `POST term/search?mode=registration` → el paso de selección de periodo. `term/search` responde `regAllowed: false, "Term not eligible for registration"` fuera de la ventana de inscripción, bloqueando el flujo → no usar para horario.
- `classRegistration/classRegistration` → redirige a `/ssb/registration/registration` (página sin `#getRegistrationEvents`).
- `registrationHistory/renderActiveRegistrations` → devuelve la inscripción **activa** y **ignora el parámetro `term`** (siempre el periodo actual) → solo útil para el periodo vigente.
- `classRegistration/getMeetingInformationForRegistrations` → lista semanal; devuelve `[]` en sesión nueva (misma limitación de periodo activo).
- `registrationHistory/getRegistrationItems` → `403 access denied`.

### Periodos (`term`)
- Obtenibles vía `GET .../ssb/term` (JSON) o del `<select id="lookupFilter">` de registrationHistory.
- Ejemplos: `202610` = "2026-I (PREGRADO)", `202690` = CENTRO DE IDIOMAS 2026, `202520`, `202510`, `202410`.
- La app usa por defecto `"202610"`.

### Archivos clave
- `services/banner_sso_service.py`: `get_horario`, `_preparar_sesion_inscripcion`, `_agrupar_horario_desde_registros`, `_hora_hhmm_a_formato`, `_desescapar_html`, `_fusionar_bloques`.
- `services/scraper_service.py`: `login()` (SSO primero, fallback ASP.NET legado), `ACTIVE_SESSIONS`.
- `main.py`: endpoint `/horario`.
- `test_horario_e2e.py`: prueba end-to-end (login real + raw `reset` + parseo + varios periodos).

## Notas / asistencia
- Portales: `campusvirtual.upao.edu.pe` (Notas) y `ssb.upao.edu.pe/StudentSelfService` (studentGrades, studentAttendanceTracking). Funcionales; no tocar.

## Contrato con la app Android
- `HorarioResponse{success, periodo, total_cursos, total_bloques, cursos}`
- `HorarioCurso{crn, codigo_materia, numero_curso, nombre, bloques}`
- `HorarioBloque{dia (0-6, LUN=0 — solo informativo; la app usa dia_nombre), dia_nombre, hora_inicio, hora_fin, hora_inicio_12h, hora_fin_12h, aula}`
- App consume `https://upaos.onrender.com/`.
