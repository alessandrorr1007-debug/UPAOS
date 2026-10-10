# Actualización de seguridad

Las rutas y los formatos de respuesta se conservan. Todas las rutas privadas
requieren `Authorization: Bearer <token>`. El campo `usuario` debe coincidir con
la cuenta autenticada. La app actualizada añade ese encabezado automáticamente,
incluyendo los trabajos en segundo plano y el registro de FCM.

## Validación local

```powershell
venv\Scripts\python.exe -m unittest test_security -v
venv\Scripts\python.exe test_admin_auth.py
venv\Scripts\python.exe smoke_features_test.py
```

Estas pruebas usan bases temporales y no consultan las cuentas reales de UPAO.

## Publicación coordinada

1. Respaldar la base de datos y la clave de cifrado existente.
2. Distribuir la app actualizada antes de activar el backend actualizado.
   Las apps antiguas no envían sesión a todas las rutas privadas.
3. Mantener la misma `FERNET_KEY` en producción. Si ya existe un administrador,
   su hash de contraseña se conserva; no se restablece en cada arranque.
   Para una instalación nueva, configurar `ADMIN_PASSWORD` con un valor privado.
4. Los tokens anteriores dejan de ser válidos. La app puede recuperar la sesión
   con sus credenciales guardadas; si no las tiene, se requiere iniciar sesión.

Las sesiones nuevas tienen tokens aleatorios, guardados únicamente como hashes
en `auth_sessions`, y vencen a los 30 días. La tabla se crea automáticamente.
Las cookies de Banner siguen en memoria, pero una sesión válida de la API puede
reconectar después de un reinicio usando las credenciales cifradas.

Para SQLite local sin `FERNET_KEY`, se genera una clave junto a la base con
extensión `.fernet.key`. Respaldar ese archivo junto con la base; no subirlo a Git.
Las credenciales cifradas con la antigua clave pública predeterminada se migran
automáticamente. Una clave configurada inválida genera un error explícito en
lugar de sustituirse por una clave temporal que perdería las credenciales.

En Android se migran las preferencias antiguas al almacenamiento cifrado antes
de limpiar el respaldo sin cifrar. Las preferencias de sesión se excluyen del
backup y de la transferencia de dispositivos. No se registran cuerpos de login
ni tokens en los logs modificados.

No se cambió la interfaz, la fórmula de notas ni la integración con Canvas.
Las pruebas locales no sustituyen una comprobación en un teléfono y con Banner
real antes de publicar.

## Correcciones de inicio de sesión

Los rechazos explícitos del SSO devuelven `error_code=invalid_credentials` y
`necesita_captcha=false`. Solo se intenta el portal alternativo cuando el SSO
no está disponible. Las redirecciones inesperadas ya no se consideran un login
correcto. Se distinguen las credenciales incorrectas de los fallos de conexión.

Un captcha auténtico incluye `captcha_id`; la app lo devuelve a
`/login/confirmar-captcha` junto con el código. El backend conserva durante cinco
minutos la misma sesión y los campos ocultos que generaron la imagen. El reto
es de un solo uso y pertenece a una cuenta. Si el backend se reinicia durante
ese paso, el usuario debe iniciar el login nuevamente.

La app centraliza los mensajes de error y la renovación de sesión. El worker
ya no repite los reintentos de login del interceptor. Las ejecuciones simultáneas
se evitan y los snapshots de notificaciones se separan por cuenta. La primera
revisión después de esta actualización establece una nueva base de comparación.
Cerrar sesión ya no selecciona automáticamente la primera cuenta guardada al
reabrir la app; los controles de guardar contraseña y mantener sesión se respetan.
