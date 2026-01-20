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
ESIK_DEGERI = 0.8  # %0.8 anlık hareket olunca haber ver

# ==============================================================================
# 🎯 FULL 1:1 STRATEJİ (EMTİA + TEKNOLOJİ)
# ==============================================================================
STRATEJI_MAP = {
    # --- 🥇 EMTİALAR (Tablodaki Liste) ---
    "ALTIN_TR":  {"Sinyal": "GC=F", "Hedef": "GLDTR.IS", "Ad": "Altın (TR)",   "Piyasa": "BIST"},
    "ALTIN_US":  {"Sinyal": "GC=F", "Hedef": "GLD",      "Ad": "Altın (ABD)",  "Piyasa": "ABD"},
    
    "GUMUS_TR":  {"Sinyal": "SI=F", "Hedef": "GMSTR.IS", "Ad": "Gümüş (TR)",   "Piyasa": "BIST"},
    "GUMUS_US":  {"Sinyal": "SI=F", "Hedef": "SLV",      "Ad": "Gümüş (ABD)",  "Piyasa": "ABD"},
    
    "PETROL_US": {"Sinyal": "CL=F", "Hedef": "USO",      "Ad": "Petrol",       "Piyasa": "ABD"},
    "GAZ_US":    {"Sinyal": "NG=F", "Hedef": "UNG",      "Ad": "Doğalgaz",     "Piyasa": "ABD"},
    "BAKIR_US":  {"Sinyal": "HG=F", "Hedef": "CPER",     "Ad": "Bakır",        "Piyasa": "ABD"},
    "MISIR_US":  {"Sinyal": "ZC=F", "Hedef": "CORN",     "Ad": "Mısır",        "Piyasa": "ABD"},
    "BUGDAY_US": {"Sinyal": "ZW=F", "Hedef": "WEAT",     "Ad": "Buğday",       "Piyasa": "ABD"},

    # --- 💻 TEKNOLOJİ & ENDEKSLER (Forvet Hattı) ---
    "NASDAQ_TR": {"Sinyal": "NQ=F", "Hedef": "NASDQQ.IS","Ad": "Nasdaq (TR)", "Piyasa": "BIST"},
    "NASDAQ_US": {"Sinyal": "NQ=F", "Hedef": "QQQ",      "Ad": "Nasdaq (ABD)", "Piyasa": "ABD"},
    "SP500_US":  {"Sinyal": "ES=F", "Hedef": "SPY",      "Ad": "S&P 500",      "Piyasa": "ABD"}
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

def piyasa_verisi_al(sembol):
    """
    Hem anlık fiyatı hem de günlük % değişimini çeker.
    """
    try:
        ticker = yf.Ticker(sembol)
        hist = ticker.history(period="5d")
        
        if hist.empty:
            return None, 0.0, "⚪", "VERİ YOK"

        fiyat = hist['Close'].iloc[-1]
        
        # Günlük Değişim Hesabı (Dünkü kapanışa göre)
        if len(hist) >= 2:
            onceki_kapanis = hist['Close'].iloc[-2]
            gunluk_degisim = ((fiyat - onceki_kapanis) / onceki_kapanis) * 100
        else:
            gunluk_degisim = 0.0

        # Piyasa Durumu (Basit simülasyon)
        durum_ikon = "🟢" # GitHub'da canlı veri çekebiliyorsak açıktır varsayımı
        durum_metin = "AÇIK"
            
        return fiyat, gunluk_degisim, durum_ikon, durum_metin

    except Exception as e:
        return None, 0.0, "⚪", "HATA"

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
    print("🌍 Bot Başlatıldı (Görsel Formatlı Mod)...")
    
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    su_an = time.time()

    for key, detay in STRATEJI_MAP.items():
        
        # 1. SİNYAL (FUTURES) VERİSİ
        sinyal_kod = detay["Sinyal"]
        sinyal_fiyat, sinyal_gunluk, sinyal_ikon, sinyal_durum = piyasa_verisi_al(sinyal_kod)
        
        if sinyal_fiyat is None: continue

        # Hafıza Kontrolü (Anlık Hareket İçin)
        eski_veri = hafiza.get(sinyal_kod, {})
        eski_sinyal_fiyat = eski_veri.get("son_fiyat")

        # Hile Modu (İlk çalışmada tetiklensin diye)
        if eski_sinyal_fiyat is None:
            eski_sinyal_fiyat = sinyal_fiyat * 0.95 
            print(f"😈 İlk Tanışma: {key}")

        # ANLIK HAREKET (Son kontrolden beri ne oldu?)
        anlik_hareket = ((sinyal_fiyat - eski_sinyal_fiyat) / eski_sinyal_fiyat) * 100
        
        # Loglama
        if abs(anlik_hareket) > 0.1:
            print(f"🔍 {key}: Anlık %{anlik_hareket:.2f} | Günlük %{sinyal_gunluk:.2f}")

        # 🔥 EŞİK GEÇİLDİ Mİ?
        if abs(anlik_hareket) >= ESIK_DEGERI:
            
            # 2. HEDEF (ETF) VERİSİ
            hedef_kod = detay["Hedef"]
            hedef_fiyat, hedef_gunluk, hedef_ikon, hedef_durum = piyasa_verisi_al(hedef_kod)
            hedef_rsi = rsi_hesapla(hedef_kod)
            
            # AI Analizi
            paket = {
                "tur": "ARBITRAJ",
                "emtia_adi": detay['Ad'],
                "sembol": hedef_kod,
                "anlik_hareket": round(anlik_hareket, 2),
                "gunluk_degisim": round(sinyal_gunluk, 2),
                "hedef_fiyat": round(hedef_fiyat, 2) if hedef_fiyat else 0,
                "hedef_gunluk": round(hedef_gunluk, 2),
                "rsi": round(hedef_rsi, 0),
                "soru": f"Global sinyal ({sinyal_kod}) anlık %{anlik_hareket:.2f} hareket etti. Hedef varlık {hedef_kod} durumu: Fiyat {hedef_fiyat}, RSI {hedef_rsi}. Fırsat var mı?"
            }
            
            try: ai_sonuc = ai.yorumla(paket)
            except: ai_sonuc = "Analiz yapılamadı."

            # İkon Seçimi
            baslik_ikon = "🔔" 
            if abs(anlik_hareket) > 2.0: baslik_ikon = "🚨"

            # ✅ İŞTE İSTEDİĞİN GÖRSEL FORMAT
            mesaj = (
                f"{baslik_ikon} <b>HAREKET: {detay['Ad']} ({sinyal_kod})</b>\n"
                f"Durum: {sinyal_ikon} {sinyal_durum}\n\n"
                f"📊 <b>Anlık Hareket:</b> %{anlik_hareket:.2f}\n"
                f"📅 <b>Günlük Değişim:</b> %{sinyal_gunluk:.2f}\n"
                f"💵 <b>Fiyat:</b> {sinyal_fiyat:.2f}\n"
                f"------------------------\n"
                f"💰 <b>ETF/Hisse:</b> {hedef_kod}\n"
                f"🏷️ <b>ETF Fiyat:</b> {hedef_fiyat}$ ({hedef_ikon} {hedef_durum})\n"
                f"📉 <b>ETF Günlük:</b> %{hedef_gunluk:.2f}\n"
                f"📈 <b>RSI:</b> {hedef_rsi}\n\n"
                f"🤖 <b>AI:</b> {ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {key}")
            
            # Hafıza Güncelle
            yeni_hafiza[sinyal_kod] = {"son_fiyat": sinyal_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
            # Hareket yoksa eskiyi koru
            if eski_sinyal_fiyat is not None:
                if sinyal_kod not in yeni_hafiza:
                    yeni_hafiza[sinyal_kod] = eski_veri
            else:
                yeni_hafiza[sinyal_kod] = {"son_fiyat": sinyal_fiyat, "son_mesaj_zamani": su_an}
                degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(yeni_hafiza)
        print("💾 Hafıza güncellendi.")

if __name__ == "__main__":
    main()
