import firebase_admin
from firebase_admin import credentials, messaging
import logging

logger = logging.getLogger(__name__)

def initialize_firebase():
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")

def send_push_notification(token: str, title: str, body: str, data: dict = None):
    if not firebase_admin._apps:
        return

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data,
        token=token,
    )
    try:
        response = messaging.send(message)
        logger.info(f"Successfully sent push notification: {response}")
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")