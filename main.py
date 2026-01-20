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

STRATEJI_MAP = {
    # --- 🥇 EMTİALAR ---
    "ALTIN_TR":  {"Sinyal": "GC=F", "Hedef": "GLDTR.IS", "Ad": "Altın (TR)",   "Piyasa": "BIST"},
    "ALTIN_US":  {"Sinyal": "GC=F", "Hedef": "GLD",      "Ad": "Altın (ABD)",  "Piyasa": "ABD"},
    
    "GUMUS_TR":  {"Sinyal": "SI=F", "Hedef": "GMSTR.IS", "Ad": "Gümüş (TR)",   "Piyasa": "BIST"},
    "GUMUS_US":  {"Sinyal": "SI=F", "Hedef": "SLV",      "Ad": "Gümüş (ABD)",  "Piyasa": "ABD"},
    
    "PETROL_US": {"Sinyal": "CL=F", "Hedef": "USO",      "Ad": "Petrol",       "Piyasa": "ABD"},
    "GAZ_US":    {"Sinyal": "NG=F", "Hedef": "UNG",      "Ad": "Doğalgaz",     "Piyasa": "ABD"},
    "BAKIR_US":  {"Sinyal": "HG=F", "Hedef": "CPER",     "Ad": "Bakır",        "Piyasa": "ABD"},
    "MISIR_US":  {"Sinyal": "ZC=F", "Hedef": "CORN",     "Ad": "Mısır",        "Piyasa": "ABD"},
    "BUGDAY_US": {"Sinyal": "ZW=F", "Hedef": "WEAT",     "Ad": "Buğday",       "Piyasa": "ABD"},

    # --- 💻 TEKNOLOJİ & ENDEKSLER ---
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

def istatistik_hesapla(hist_data):
    """
    Son 100 güne bakar:
    1. Ortalama kaç gün üst üste düşmüş?
    2. Şu an kaçıncı düşüş gününde?
    """
    try:
        # Yüzdelik değişimleri al
        returns = hist_data['Close'].pct_change().dropna()
        # Son 100 işlem gününü al
        last_100 = returns.tail(100)
        
        negatif_seriler = []
        gecici_seri = 0
        
        # 1. Geçmiş Serileri Hesapla
        for degisim in last_100:
            if degisim < 0:
                gecici_seri += 1
            else:
                if gecici_seri > 0:
                    negatif_seriler.append(gecici_seri)
                gecici_seri = 0 # Sıfırla
        
        # Ortalama Negatif Seri Uzunluğu
        if len(negatif_seriler) > 0:
            ort_negatif = sum(negatif_seriler) / len(negatif_seriler)
        else:
            ort_negatif = 0
            
        # 2. Mevcut Seriyi Hesapla (Sondan geriye say)
        mevcut_seri = 0
        for degisim in reversed(last_100):
            if degisim < 0:
                mevcut_seri += 1
            else:
                break
                
        return f"{ort_negatif:.2f}", mevcut_seri
        
    except:
        return "0.00", 0

def piyasa_verisi_al(sembol):
    try:
        ticker = yf.Ticker(sembol)
        # İstatistik için 6 aylık veri çekiyoruz (100 günü garanti etmek için)
        hist = ticker.history(period="6mo")
        
        if hist.empty:
            return None, 0.0, "⚪", "VERİ YOK", "0.00", 0

        fiyat = hist['Close'].iloc[-1]
        
        # Günlük Değişim
        if len(hist) >= 2:
            onceki_kapanis = hist['Close'].iloc[-2]
            gunluk_degisim = ((fiyat - onceki_kapanis) / onceki_kapanis) * 100
        else:
            gunluk_degisim = 0.0

        durum_ikon = "🟢" 
        durum_metin = "AÇIK"
        
        # 🔥 YENİ: İstatistik Hesapla
        ort_seri, mevcut_seri = istatistik_hesapla(hist)
            
        return fiyat, gunluk_degisim, durum_ikon, durum_metin, ort_seri, mevcut_seri

    except Exception as e:
        return None, 0.0, "⚪", "HATA", "0.00", 0

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
    print("🌍 Bot Başlatıldı (İstatistik & Mean Reversion Modu)...")
    
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    su_an = time.time()

    for key, detay in STRATEJI_MAP.items():
        
        # 1. SİNYAL (FUTURES)
        # Sinyal için istatistiğe gerek yok, _ ile geçiyoruz
        sinyal_kod = detay["Sinyal"]
        sinyal_fiyat, sinyal_gunluk, sinyal_ikon, sinyal_durum, _, _ = piyasa_verisi_al(sinyal_kod)
        
        if sinyal_fiyat is None: continue

        eski_veri = hafiza.get(sinyal_kod, {})
        eski_sinyal_fiyat = eski_veri.get("son_fiyat")

        if eski_sinyal_fiyat is None:
            eski_sinyal_fiyat = sinyal_fiyat * 0.95 
            print(f"😈 İlk Tanışma: {key}")

        anlik_hareket = ((sinyal_fiyat - eski_sinyal_fiyat) / eski_sinyal_fiyat) * 100
        
        if abs(anlik_hareket) > 0.1:
            print(f"🔍 {key}: Anlık %{anlik_hareket:.2f}")

        # 🔥 HAREKET VARSA
        if abs(anlik_hareket) >= ESIK_DEGERI:
            
            # 2. HEDEF (ETF/HISSE) - İstatistik Burada Önemli
            hedef_kod = detay["Hedef"]
            # Verileri al (ort_seri ve mevcut_seri eklendi)
            hedef_fiyat, hedef_gunluk, hedef_ikon, hedef_durum, ort_seri, mevcut_seri = piyasa_verisi_al(hedef_kod)
            hedef_rsi = rsi_hesapla(hedef_kod)
            
            # Formatlama
            fmt_hedef_fiyat = f"{hedef_fiyat:.2f}" if hedef_fiyat else "0.00"
            fmt_rsi = f"{hedef_rsi:.0f}" if hedef_rsi else "50"
            
            # AI Analiz Paketi
            paket = {
                "tur": "ARBITRAJ",
                "emtia_adi": detay['Ad'],
                "sembol": hedef_kod,
                "anlik_hareket": round(anlik_hareket, 2),
                "gunluk_degisim": round(sinyal_gunluk, 2),
                "hedef_fiyat": float(fmt_hedef_fiyat),
                "hedef_gunluk": round(hedef_gunluk, 2),
                "rsi": int(float(fmt_rsi)),
                # İstatistiği AI'ya da söyleyelim
                "negatif_seri_ort": ort_seri,
                "mevcut_negatif_seri": mevcut_seri,
                "soru": f"Global sinyal %{anlik_hareket:.2f} hareketli. Hedef {hedef_kod} son 100 günde ortalama {ort_seri} gün düşüş serisi yapmış, şu an {mevcut_seri}. gündeyiz. Dönüş (Reversal) yakın mı?"
            }
            
            try: ai_sonuc = ai.yorumla(paket)
            except: ai_sonuc = "Analiz yapılamadı."

            baslik_ikon = "🔔" 
            if abs(anlik_hareket) > 2.0: baslik_ikon = "🚨"

            # 🛠️ GÖRSEL FORMAT (İstatistik Eklendi)
            mesaj = (
                f"{baslik_ikon} <b>HAREKET: {detay['Ad']} ({sinyal_kod})</b>\n"
                f"Durum: {sinyal_ikon} {sinyal_durum}\n\n"
                f"📊 <b>Anlık Hareket:</b> %{anlik_hareket:.2f}\n"
                f"📅 <b>Günlük Değişim:</b> %{sinyal_gunluk:.2f}\n"
                f"💵 <b>Fiyat:</b> {sinyal_fiyat:.2f}\n"
                f"------------------------\n"
                f"💰 <b>ETF/Hisse:</b> {hedef_kod}\n"
                f"🏷️ <b>ETF Fiyat:</b> {fmt_hedef_fiyat}$ ({hedef_ikon} {hedef_durum})\n"
                f"📉 <b>ETF Günlük:</b> %{hedef_gunluk:.2f}\n"
                f"📈 <b>RSI:</b> {fmt_rsi}\n"
                f"🛑 <b>Negatif Seri:</b> Ort. {ort_seri} / {mevcut_seri} gün\n\n"
                f"🤖 <b>AI:</b> {ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {key}")
            
            yeni_hafiza[sinyal_kod] = {"son_fiyat": sinyal_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
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
