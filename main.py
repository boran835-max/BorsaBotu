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
    "NI=F":  {"Ad": "Nikel",           "ETF": "NIKL"}, 
    "ALI=F": {"Ad": "Alüminyum",       "ETF": "AA"},   

    # --- 🛢️ ENERJİ ---
    "CL=F": {"Ad": "Ham Petrol (WTI)", "ETF": "USO"},
    "BZ=F": {"Ad": "Brent Petrol",     "ETF": "BNO"},  
    "NG=F": {"Ad": "Doğalgaz",         "ETF": "UNG"},
    "RB=F": {"Ad": "Benzin",           "ETF": "UGA"},  

    # --- 🌾 TARIM & GIDA (Softs) ---
    "ZC=F": {"Ad": "Mısır",       "ETF": "CORN"},
    "ZW=F": {"Ad": "Buğday",      "ETF": "WEAT"},
    "ZS=F": {"Ad": "Soya",        "ETF": "SOYB"},
    "KC=F": {"Ad": "Kahve",       "ETF": "JO"},    
    "SB=F": {"Ad": "Şeker",       "ETF": "CANE"},  
    "CC=F": {"Ad": "Kakao",       "ETF": "NIB"},   
    "CT=F": {"Ad": "Pamuk",       "ETF": "BAL"}    
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
    Yahoo Finance'den hem fiyatı, hem değişimi hem de market durumunu çeker.
    Web sitesindeki verilerle eşleşmesi için .info kullanır.
    """
    try:
        ticker = yf.Ticker(sembol)
        # .info verisi en detaylısıdır (marketState içerir)
        bilgi = ticker.info 
        
        # Fiyatı ve Önceki Kapanışı al
        fiyat = bilgi.get('regularMarketPrice')
        
        # Eğer info boş dönerse (bazen olur), fast_info'ya geç (Yedek Plan)
        if fiyat is None:
            fiyat = ticker.fast_info.last_price
            onceki_kapanis = ticker.fast_info.previous_close
        else:
            onceki_kapanis = bilgi.get('regularMarketPreviousClose')
            
        # Günlük Değişimi Hesapla (Yahoo Mantığı: (Son - Dün) / Dün)
        if onceki_kapanis and onceki_kapanis > 0:
            gunluk_degisim = ((fiyat - onceki_kapanis) / onceki_kapanis) * 100
        else:
            gunluk_degisim = 0.0

        # Piyasa Durumu (Açık mı Kapalı mı?)
        durum_kodu = bilgi.get('marketState', 'CLOSED')
        
        if durum_kodu == "REGULAR":
            ikon = "🟢"
            metin = "AÇIK"
        else:
            ikon = "⚪"
            metin = "KAPALI"
            
        return fiyat, gunluk_degisim, ikon, metin

    except Exception as e:
        # Hata durumunda veri yok dön
        return None, 0.0, "⚪", "VERİ YOK"

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
    print("🌍 Bot Başlatıldı (Dev Kadro, Yahoo Senkronize & Market Durumu)...")
    
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        # Emtia için verileri çek
        guncel_fiyat, gunluk_degisim_orani, emtia_ikon, emtia_durum = piyasa_verisi_al(kaynak_kodu)
        
        if guncel_fiyat is None: 
            continue

        eski_veri = hafiza.get(kaynak_kodu, {})
        eski_fiyat = eski_veri.get("son_fiyat")

        # 😈 HİLE MODU: İlk kez görüyorsak %5 düşükmüş gibi davran
        if eski_fiyat is None:
            eski_fiyat = guncel_fiyat * 0.95 
            eski_veri = {"son_fiyat": eski_fiyat}
            print(f"😈 İlk Tanışma Hilesi: {detay['Ad']}")

        # Botun kendi referansına göre anlık hareket hesaplaması
        degisim_yuzdesi = ((guncel_fiyat - eski_fiyat) / eski_fiyat) * 100
        
        # Sadece büyük hareketleri ekrana yaz
        if abs(degisim_yuzdesi) >= ESIK_DEGERI:
            print(f"🔥 {detay['Ad']}: %{degisim_yuzdesi:.2f}")

            etf_kodu = detay["ETF"]
            
            # ETF Verilerini Çek (Fiyat, Yüzde, Durum)
            etf_fiyat, etf_degisim, etf_ikon, etf_durum = piyasa_verisi_al(etf_kodu)
            etf_rsi = rsi_hesapla(etf_kodu)
            
            paket = {
                "tur": "EMTIA", 
                "emtia_adi": f"{detay['Ad']}",
                "sembol": etf_kodu,
                "emtia_degisim": round(degisim_yuzdesi, 2),
                "hisse_degisim": round(etf_degisim, 2),
                "fiyat": round(etf_fiyat, 2) if etf_fiyat else "Veri Yok",
                "rsi": round(etf_rsi, 0),
                "trend": "YÜKSELİŞ" if degisim_yuzdesi > 0 else "DÜŞÜŞ"
            }
            
            try: ai_sonuc = ai.yorumla(paket)
            except: ai_sonuc = ".."

            baslik_ikon = "🚨 BİLGİLENDİRME" if abs(degisim_yuzdesi) > 2.0 else "🔔 HAREKET"
            
            # Mesaj Formatı (Seçenek A uygulandı: Kapalı olsa bile yüzdeyi gösteriyoruz)
            mesaj = (
                f"<b>{baslik_ikon}: {detay['Ad']} ({kaynak_kodu})</b>\n"
                f"Durum: {emtia_ikon} {emtia_durum}\n\n"
                f"📊 <b>Anlık Hareket:</b> %{paket['emtia_degisim']}\n"
                f"📅 <b>Günlük Değişim:</b> %{gunluk_degisim_orani:.2f}\n"
                f"💵 <b>Fiyat:</b> {guncel_fiyat:.2f}\n"
                f"------------------------\n"
                f"💰 <b>ETF/Hisse:</b> {etf_kodu}\n"
                f"🏷️ <b>ETF Fiyat:</b> {paket['fiyat']}$ ({etf_ikon} {etf_durum})\n"
                f"📉 <b>ETF Günlük:</b> %{paket['hisse_degisim']}\n"
                f"📈 <b>RSI:</b> {paket['rsi']}\n\n"
                f"🤖 <b>AI:</b> {ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {detay['Ad']}")
            
            # Yeni fiyatı hafızaya yaz
            yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
            if eski_fiyat is not None:
                yeni_hafiza[kaynak_kodu] = eski_veri
            else:
                yeni_hafiza[kaynak_kodu] = {"son_fiyat": guncel_fiyat, "son_mesaj_zamani": su_an}
                degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(yeni_hafiza)
        print("💾 Hafıza güncellendi.")

if __name__ == "__main__":
    main()
