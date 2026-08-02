import os
import json
import firebase_admin
from firebase_admin import credentials, messaging

class NotificationService:
    def __init__(self):
        self.initialized = False
        self._init_firebase()

    def _init_firebase(self):
        try:
            if firebase_admin._apps:
                self.initialized = True
                return

            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "upaos-a7f19-firebase-adminsdk-fbsvc-632fb67943.json")
            cred_json_env = os.getenv("FIREBASE_CREDENTIALS_JSON")

            if cred_json_env:
                print("[Firebase Log] Inicializando SDK usando variable de entorno FIREBASE_CREDENTIALS_JSON...")
                cred_dict = json.loads(cred_json_env)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                self.initialized = True
            elif os.path.exists(cred_path):
                print(f"[Firebase Log] Inicializando SDK desde archivo de clave local: {cred_path}...")
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
                self.initialized = True
            else:
                print(f"[Firebase Warning] No se encontró el archivo de clave '{cred_path}' ni la variable FIREBASE_CREDENTIALS_JSON.")
        except Exception as e:
            print(f"[Firebase Error] Error al inicializar Firebase Admin SDK: {e}")

    def send_push_notification(self, token: str, title: str, body: str, data: dict = None) -> bool:
        if not self.initialized:
            print("[Firebase Warning] No se envió notificación push: Firebase Admin SDK no está inicializado.")
            return False

        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data or {},
                token=token
            )
            response = messaging.send(message)
            print(f"[Firebase Log] Notificación push enviada con éxito. Message ID: {response}")
            return True
        except Exception as e:
            print(f"[Firebase Error] Error al enviar notificación a token '{token[:15]}...': {e}")
            return False

notification_service = NotificationService()
