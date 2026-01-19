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
ESIK_DEGERI = 0.8  # Her %0.8'lik harekette yeni mesaj gelir.
# SPAM_SURESI'ni kaldırdık! Artık zaman değil, fiyat konuşur.

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
        # 5 Günlük veri (Garanti olsun diye)
        data = ticker.history(period="5d")
        if data.empty: return None
        return data['Close'].iloc[-1]
    except: return None

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
    print("🌍 Bot Başlatıldı (Ralli Dostu Mod - Zaman Sınırı YOK)...")
    
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    
    # Şu anki zamanı sadece log için tutuyoruz, kısıtlama için değil
    su_an = time.time() 

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        guncel_fiyat = fiyat_getir(kaynak_kodu)
        if guncel_fiyat is None: 
            print(f"⚠️ Veri yok: {kaynak_kodu}")
            continue

        eski_veri = hafiza.get(kaynak_kodu, {})
        eski_fiyat = eski_veri.get("son_fiyat")

        # 😈 HİLE MODU (Test İçin):
        # Hafızada kayıt yoksa, eski fiyatı %5 düşük farz et ki mesaj atsın.
        if eski_fiyat is None:
            eski_fiyat = guncel_fiyat * 0.95 
            eski_veri = {"son_fiyat": eski_fiyat} 
            print(f"😈 İlk Çalışma Hilesi: {kaynak_kodu}")

        # Hesaplama
        degisim_yuzdesi = ((guncel_fiyat - eski_fiyat) / eski_fiyat) * 100
        print(f"🔍 {kaynak_kodu}: Fark=%{degisim_yuzdesi:.2f}")

        # 🔥 KARAR ANI: Sadece Fiyata Bakıyoruz! Zaman kuralı YOK.
        if abs(degisim_yuzdesi) >= ESIK_DEGERI:
            
            etf_kodu = detay["ETF"]
            etf_fiyat = fiyat_getir(etf_kodu)
            etf_rsi = rsi_hesapla(etf_kodu)
            
            paket = {
                "tur": "HISSE", 
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

            baslik_ikon = "🚨 RALLİ/ÇÖKÜŞ" if abs(degisim_yuzdesi) > 2.0 else "🔔 HAREKET"
            
            mesaj = (
                f"<b>{baslik_ikon}: {detay['Ad']} Durmuyor!</b>\n\n"
                f"📊 <b>Son Değişim:</b> %{paket['emtia_degisim']}\n"
                f"💵 <b>Fiyat:</b> {guncel_fiyat:.2f}\n"
                f"💰 <b>ETF:</b> {etf_kodu} ({paket['fiyat']}$)\n"
                f"------------------------\n"
                f"📈 <b>RSI:</b> {paket['rsi']}\n"
                f"🤖 <b>AI:</b> {ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {kaynak_kodu}")
            
            # ✅ KRİTİK NOKTA: Mesaj attığımız için referans fiyatı GÜNCELLİYORUZ.
            # Artık yeni %0.8'lik hareket bu fiyata göre hesaplanacak.
            yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
            # Hareket küçükse (%0.8 altı), eski referans fiyatı KORU.
            # Böylece gıdım gıdım artışları kaçırmayız.
            yeni_hafiza[kaynak_kodu] = eski_veri # Değişiklik yok
            
            # (Teknik detay: Eğer eski_veri boşsa, yani ilk çalışmada %0.8 altı kaldıysa
            # o zaman kaydetmeliyiz ki bir dahakine referans olsun)
            if eski_fiyat is None: # Bu blok hile modu olduğu için pek çalışmaz ama güvenlik olsun.
                 yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
                 degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(yeni_hafiza)
        print("💾 Hafıza güncellendi.")

if __name__ == "__main__":
    main()
