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
ESIK_DEGERI = 0.8  # %0.8 hareket olunca haber ver
# SPAM SÜRESİ YOK! Ralli varsa her adımda mesaj atar.

# ==============================================================================
# 🛡️ DEV EMTİA LİSTESİ (INVESTING.COM UYUMLU)
# ==============================================================================
STRATEJI_MAP = {
    # --- 🥇 DEĞERLİ METALLER ---
    "GC=F": {"Ad": "Altın",       "ETF": "GLD"},
    "SI=F": {"Ad": "Gümüş",       "ETF": "SLV"},
    "PL=F": {"Ad": "Platin",      "ETF": "PPLT"},
    "PA=F": {"Ad": "Paladyum",    "ETF": "PALL"},

    # --- 🏗️ ENDÜSTRİYEL METALLER (Senin İsteklerin) ---
    "HG=F":  {"Ad": "Bakır",           "ETF": "CPER"},
    "NI=F":  {"Ad": "Nikel",           "ETF": "NIKL"}, # Nikel ETF'i
    "ALI=F": {"Ad": "Alüminyum",       "ETF": "AA"},   # JJU kapandığı için Alcoa (AA) hissesini koyduk

    # --- 🛢️ ENERJİ ---
    "CL=F": {"Ad": "Ham Petrol (WTI)", "ETF": "USO"},
    "BZ=F": {"Ad": "Brent Petrol",     "ETF": "BNO"},  # Brent eklendi
    "NG=F": {"Ad": "Doğalgaz",         "ETF": "UNG"},
    "RB=F": {"Ad": "Benzin",           "ETF": "UGA"},  # Benzin eklendi

    # --- 🌾 TARIM & GIDA (Softs) ---
    "ZC=F": {"Ad": "Mısır",       "ETF": "CORN"},
    "ZW=F": {"Ad": "Buğday",      "ETF": "WEAT"},
    "ZS=F": {"Ad": "Soya",        "ETF": "SOYB"},
    "KC=F": {"Ad": "Kahve",       "ETF": "JO"},    # Kahve eklendi
    "SB=F": {"Ad": "Şeker",       "ETF": "CANE"},  # Şeker eklendi
    "CC=F": {"Ad": "Kakao",       "ETF": "NIB"},   # Kakao eklendi
    "CT=F": {"Ad": "Pamuk",       "ETF": "BAL"}    # Pamuk eklendi
}

bot = TelegramBot()
ai = AITrader()

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
    try:
        ticker = yf.Ticker(sembol)
        # 5 Günlük veri çekiyoruz ki "Data Yok" hatası almayalım ve önceki günü bilelim
        data = ticker.history(period="5d")
        if data.empty: return None, 0.0
        
        son_fiyat = data['Close'].iloc[-1]
        gunluk_degisim = 0.0

        # Günlük değişimi hesaplamak için dünkü kapanışa ihtiyacımız var
        if len(data) >= 2:
            onceki_kapanis = data['Close'].iloc[-2]
            gunluk_degisim = ((son_fiyat - onceki_kapanis) / onceki_kapanis) * 100
        
        return son_fiyat, gunluk_degisim
    except: return None, 0.0

def rsi_hesapla(sembol):
    try:
        ticker = yf.Ticker(sembol)
        hist = ticker.history(period="1mo")
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
    print("🌍 Bot Başlatıldı (Dev Kadro & Hileli Mod)...")
    
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        # Artık hem fiyatı hem de günlük değişimi alıyoruz
        guncel_fiyat, gunluk_degisim_orani = fiyat_getir(kaynak_kodu)
        
        if guncel_fiyat is None: 
            # Veri yoksa sessizce geç, logu kirletme
            continue

        eski_veri = hafiza.get(kaynak_kodu, {})
        eski_fiyat = eski_veri.get("son_fiyat")

        # 😈 HİLE MODU: İlk kez görüyorsak %5 düşükmüş gibi davran
        if eski_fiyat is None:
            eski_fiyat = guncel_fiyat * 0.95 
            eski_veri = {"son_fiyat": eski_fiyat}
            print(f"😈 İlk Tanışma Hilesi: {detay['Ad']}")

        # Hesaplama (Hafızadaki fiyata göre değişim)
        degisim_yuzdesi = ((guncel_fiyat - eski_fiyat) / eski_fiyat) * 100
        
        # Sadece büyük hareketleri ekrana yaz (Buradaki değişim hafızadaki değişimi baz alır)
        if abs(degisim_yuzdesi) >= ESIK_DEGERI:
            print(f"🔥 {detay['Ad']}: %{degisim_yuzdesi:.2f}")

            etf_kodu = detay["ETF"]
            # ETF için günlük değişimi kullanmayacağız ama fonksiyon yapısı değiştiği için unpack ediyoruz
            etf_fiyat, _ = fiyat_getir(etf_kodu) 
            etf_rsi = rsi_hesapla(etf_kodu)
            
            paket = {
                "tur": "EMTIA", 
                "emtia_adi": f"{detay['Ad']}",
                "sembol": etf_kodu,
                "emtia_degisim": round(degisim_yuzdesi, 2),
                "hisse_degisim": "---",
                "fiyat": round(etf_fiyat, 2) if etf_fiyat else "Veri Yok",
                "rsi": round(etf_rsi, 0),
                "trend": "YÜKSELİŞ" if degisim_yuzdesi > 0 else "DÜŞÜŞ"
            }
            
            try: ai_sonuc = ai.yorumla(paket)
            except: ai_sonuc = ".."

            baslik_ikon = "🚨 BİLGİLENDİRME" if abs(degisim_yuzdesi) > 2.0 else "🔔 HAREKET"
            
            mesaj = (
                f"<b>{baslik_ikon}: {detay['Ad']} ({kaynak_kodu})</b>\n\n"
                f"📊 <b>Anlık Hareket:</b> %{paket['emtia_degisim']}\n"
                f"📅 <b>Günlük Değişim:</b> %{gunluk_degisim_orani:.2f}\n"
                f"💵 <b>Fiyat:</b> {guncel_fiyat:.2f}\n"
                f"💰 <b>ETF/Hisse:</b> {etf_kodu} ({paket['fiyat']}$)\n"
                f"------------------------\n"
                f"📈 <b>RSI:</b> {paket['rsi']}\n"
                f"🤖 <b>AI:</b> {ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {detay['Ad']}")
            
            # Yeni fiyatı hafızaya yaz (Referans güncelle)
            yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
            # Hareket küçükse eski referansı koru
            if eski_fiyat is not None:
                yeni_hafiza[kaynak_kodu] = eski_veri
            else:
                # Hileli modda buraya düşmez ama yine de güvenli kayıt
                yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
                degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(yeni_hafiza)
        print("💾 Hafıza güncellendi.")

if __name__ == "__main__":
    main()
