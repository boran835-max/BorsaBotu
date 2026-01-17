import requests
import os
from dotenv import load_dotenv

load_dotenv()

class TelegramBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def gonder(self, mesaj):
        if not self.token: 
            print("❌ Telegram Token Bulunamadı!")
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        
        # HTML modunu zorluyoruz
        payload = {
            "chat_id": self.chat_id, 
            "text": mesaj, 
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        try:
            response = requests.post(url, json=payload)
            if response.status_code != 200:
                print(f"❌ Telegram Hatası: {response.text}")
        except Exception as e:
            print(f"❌ Bağlantı Hatası: {e}")