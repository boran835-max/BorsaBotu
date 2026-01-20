import warnings
# Google'ın "Eski kütüphane" uyarısını gizle
warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

class AITrader:
    def __init__(self):
        # --- SENİN ORİJİNAL KODUN (DOKUNULMADI) ---
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("❌ HATA: API Key yok!")
            self.model = None
        else:
            try:
                genai.configure(api_key=self.api_key)
                safety = [{"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}]
                
                # Model seçimi (Senin istediğin mantık)
                try:
                    self.model = genai.GenerativeModel('gemini-3-pro-preview', safety_settings=safety)
                    # Test atışı yapalım (Hata varsa pro'ya düşsün)
                    self.model.generate_content("Test")
                except:
                    self.model = genai.GenerativeModel('gemini-pro', safety_settings=safety)
                
            except Exception as e:
                print(f"❌ AI Başlatılamadı: {e}")
                self.model = None

    def yorumla(self, p):
        if not self.model: return "AI Devre Dışı"

        # HATA ÖNLEYİCİ: main.py'den gelen paket boşsa patlamasın
        if not p: return "Veri Yok"

        # --- DÜZELTİLEN KISIM (İSTEDİĞİN FORMAT) ---
        
        # main.py'den gelen özel soruyu al, yoksa genel oluştur
        ozel_soru = p.get('soru', f"Öncü varlık %{p.get('anlik_hareket', 0)} değişti. Hedef varlık %{p.get('hedef_gunluk', 0)} değişti. Fırsat var mı?")

        prompt = f"""
        Sen Borsa Uzmanısın. Adın Fav.
        
        ANALİZ VERİLERİ:
        {p}
        
        SORU:
        {ozel_soru}
        
        GÖREVİN:
        Bu verileri analiz et ve aşağıdaki formatta yanıt ver.
        
        KESİN FORMAT KURALLARI:
        1. Yanıtın SADECE şu iki satırdan oluşmalı:
           YORUM: [Buraya 2-3 cümlelik, teknik ve net piyasa analizi]
           SONUÇ: [GÜÇLÜ AL / KADEMELİ AL / BEKLE / SAT / DİKKAT] (Sadece birini seç)
           
        2. Başka hiçbir metin, giriş cümlesi veya süsleme yapma.
        """

        try:
            response = self.model.generate_content(prompt)
            if not response.text: return "Yorum Yok"
            # Temizlik
            return response.text.replace("**", "").replace("*", "").strip()
        except Exception:
            return "Bağlantı Sorunu"
