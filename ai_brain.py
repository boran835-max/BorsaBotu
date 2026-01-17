import warnings
# Google'ın "Eski kütüphane" uyarısını gizle
warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

class AITrader:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("❌ HATA: API Key yok!")
            self.model = None
        else:
            try:
                genai.configure(api_key=self.api_key)
                safety = [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}]
                
                # Model seçimi
                try:
                    self.model = genai.GenerativeModel('gemini-3-pro-preview', safety_settings=safety)
                    # Test atışı yapalım (Hata varsa pro'ya düşsün)
                    self.model.generate_content("Test")
                except:
                    self.model = genai.GenerativeModel('gemini-pro', safety_settings=safety)
                
            except Exception as e:
                # Sadece kritik hataları yazdır
                print(f"❌ AI Başlatılamadı: {e}")
                self.model = None

    def yorumla(self, p):
        if not self.model: return "AI Devre Dışı"

        # HATA ÖNLEYİCİ: Eğer 'tur' anahtarı yoksa varsayılan olarak 'HISSE' say.
        tur = p.get('tur', 'HISSE') 

        # SENARYO 1: TEK VARLIK ANALİZİ (DIREKT/BANKA)
        if tur == "DIREKT":
            prompt = f"""
            Yatırım Analisti Rolü.
            VARLIK: {p.get('emtia_adi')}
            DURUM: Fiyat: {p.get('fiyat')}$ | Değişim: %{p.get('emtia_degisim')}
            TEKNİK: RSI: {p.get('rsi')} | Trend: {p.get('trend')}
            SORU: Şu an alım fırsatı mı?
            CEVAP: [GÜÇLÜ AL / KADEMELİ AL / BEKLE / SAT] - [Kısa Sebep]
            """

        # SENARYO 2: ARBİTRAJ / KIYASLAMA (HISSE/ETF)
        else:
            prompt = f"""
            Borsa Uzmanı Rolü.
            ÖNCÜ GÖSTERGE (Vadeli): {p.get('emtia_adi')} %{p.get('emtia_degisim')} yaptı.
            HEDEF VARLIK (ETF/Hisse): {p.get('sembol')} %{p.get('hisse_degisim')} yaptı.
            TEKNİK (Hedef): Fiyat: {p.get('fiyat')}$ | RSI: {p.get('rsi')}
            
            MANTIK: Öncü gösterge yükseldi ama Hedef varlık henüz yükselmediyse FIRSAT vardır.
            SORU: Bu arbitraj değerlendirilmeli mi?
            
            CEVAP FORMATI:
            YORUM: [Kısa özet]
            SONUÇ: [GÜÇLÜ AL / AL / BEKLE / SAT] (Büyük harfle)
            """

        try:
            response = self.model.generate_content(prompt)
            if not response.text: return "Yorum Yok"
            return response.text.replace("**", "").replace("*", "").strip()
        except Exception:
            return "Bağlantı Sorunu"