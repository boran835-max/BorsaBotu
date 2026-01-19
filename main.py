import warnings
warnings.filterwarnings("ignore")

import time
import os
import json 
import yfinance as yf
from ai_brain import AITrader
from notifier import TelegramBot

# ==============================================================================
# ⚙️ AYARLAR
# ==============================================================================
HAFIZA_DOSYASI = "hafiza.json"
ESIK_DEGERI = 0.8  # Yüzde kaç değişimde mesaj atsın?
SPAM_SURESI = 14400 # 4 Saat (Aynı yönde sürekli mesaj atmaması için)

# ==============================================================================
# 🛡️ STRATEJİ LİSTESİ
# ==============================================================================
STRATEJI_MAP = {
    "GC=F": {"Ad": "Altın",      "ETF": "GLD"},
    "SI=F": {"Ad": "Gümüş",      "ETF": "SLV"},
    "PL=F": {"Ad": "Platin",     "ETF": "PPLT"},
    "PA=F": {"Ad": "Paladyum",   "ETF": "PALL"},
    "HG=F": {"Ad": "Bakır",      "ETF": "CPER"},
    "CL=F": {"Ad": "Petrol (WTI)", "ETF": "USO"},
    "NG=F": {"Ad": "Doğalgaz",     "ETF": "UNG"},
    "ZW=F": {"Ad": "Buğday",     "ETF": "WEAT"},
    "ZC=F": {"Ad": "Mısır",      "ETF": "CORN"},
    "ZS=F": {"Ad": "Soya",       "ETF": "SOYB"}
}

bot = TelegramBot()
ai = AITrader()

# --- HAFIZA YÖNETİMİ ---
def hafiza_yukle():
    if os.path.exists(HAFIZA_DOSYASI):
        try:
            with open(HAFIZA_DOSYASI, "r") as f:
                return json.load(f)
        except: return {}
    return {}

def hafiza_kaydet(veri):
    with open(HAFIZA_DOSYASI, "w") as f:
        json.dump(veri, f)

def fiyat_getir(sembol):
    """Sadece anlık fiyatı getirir, geçmişe bakmaz."""
    try:
        ticker = yf.Ticker(sembol)
        # Sadece son anlık fiyatı istiyoruz
        data = ticker.history(period="1d")
        if data.empty: return None
        return data['Close'].iloc[-1]
    except: return None

def rsi_hesapla(sembol):
    """RSI için yine de biraz geçmiş veriye ihtiyacımız var (Yorum için)"""
    try:
        ticker = yf.Ticker(sembol)
        hist = ticker.history(period="1mo") # RSI için 1 ay yeterli
        if len(hist) > 14:
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi.iloc[-1]
        return 50
    except: return 50

def main():
    print("🌍 Bot Başlatıldı (Kendi Hafızasıyla Kıyaslayan Mod)...")
    
    # Hafıza Yapısı: {"GC=F": {"son_fiyat": 2000, "son_mesaj_zamani": 12345678}}
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        # 1. Anlık Fiyatı Çek
        guncel_fiyat = fiyat_getir(kaynak_kodu)
        if guncel_fiyat is None: continue

        # 2. Hafızada Eski Fiyat Var mı?
        eski_veri = hafiza.get(kaynak_kodu, {})
        eski_fiyat = eski_veri.get("son_fiyat")

        # Eğer ilk kez çalışıyorsa (Hafıza yoksa)
        if eski_fiyat is None:
            print(f"🆕 İlk kayıt: {kaynak_kodu} -> {guncel_fiyat}")
            yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": 0}
            degisiklik_var_mi = True
            continue # İlk turda mesaj atmaz, sadece kaydeder

        # 3. Kıyaslama (Bizim Matematiğimiz)
        degisim_yuzdesi = ((guncel_fiyat - eski_fiyat) / eski_fiyat) * 100
        
        print(f"🔍 {kaynak_kodu}: Eski={eski_fiyat:.2f}, Yeni={guncel_fiyat:.2f}, Fark=%{degisim_yuzdesi:.2f}")

        # 4. Karar Anı
        if abs(degisim_yuzdesi) >= ESIK_DEGERI:
            
            # Spam Kontrolü (Zaman Bazlı)
            son_mesaj_zamani = eski_veri.get("son_mesaj_zamani", 0)
            if (su_an - son_mesaj_zamani) < SPAM_SURESI:
                print(f"🛑 Süre dolmadı: {kaynak_kodu}")
                # Fiyatı güncellemeliyiz ki referansımız hep taze kalsın mı? 
                # HAYIR. Referans mesaj attığımız fiyat olmalı.
                continue

            # Mesaj At!
            etf_kodu = detay["ETF"]
            etf_fiyat = fiyat_getir(etf_kodu)
            etf_rsi = rsi_hesapla(etf_kodu)
            
            # AI Paketi
            paket = {
                "tur": "HISSE", 
                "emtia_adi": f"{detay['Ad']} (Kendi Takibim)",
                "sembol": etf_kodu,
                "emtia_degisim": round(degisim_yuzdesi, 2),
                "hisse_degisim": "---", # Bunu hesaplamadık çünkü ETF'nin eski fiyatını tutmuyoruz
                "fiyat": round(etf_fiyat, 2) if etf_fiyat else "Veri Yok",
                "rsi": round(etf_rsi, 0),
                "trend": "YÜKSELİŞ" if degisim_yuzdesi > 0 else "DÜŞÜŞ"
            }
            
            try:
                ai_sonuc = ai.yorumla(paket)
            except: ai_sonuc = ".."

            baslik_ikon = "🚨 GÜÇLÜ SİNYAL" if abs(degisim_yuzdesi) > 1.5 else "🔔 SİNYAL"
            
            mesaj = (
                f"<b>{baslik_ikon}: {detay['Ad']} Hareketlendi!</b>\n\n"
                f"📊 <b>Bizim Tespitimiz:</b> %{paket['emtia_degisim']}\n"
                f"💵 <b>Eski:</b> {eski_fiyat:.2f} -> <b>Yeni:</b> {guncel_fiyat:.2f}\n"
                f"💰 <b>İlgili ETF:</b> {etf_kodu} ({paket['fiyat']}$)\n"
                f"------------------------\n"
                f"📈 <b>RSI:</b> {paket['rsi']}\n"
                f"🤖 <b>AI:</b> {ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {kaynak_kodu}")
            
            # Yeni referans noktamız artık bu fiyat oldu
            yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
            # Fiyat değişmedi (%0.8 olmadı).
            # Peki referans fiyatı güncellemeli miyiz?
            # STRATEJİ: Hayır. Referans fiyat, en son "Oldu!" dediğimiz fiyattır.
            # Böylece fiyat gıdım gıdım artarsa (%0.2 + %0.2 + %0.2 + %0.2) toplamda %0.8 olunca yakalarız.
            pass

    if degisiklik_var_mi:
        hafiza_kaydet(yeni_hafiza)
        print("💾 Hafıza güncellendi.")

if __name__ == "__main__":
    main()
