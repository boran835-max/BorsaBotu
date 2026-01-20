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

# ==============================================================================
# 🎯 1:1 KORELASYON HARİTASI (TR & US BİRLİKTE)
# ==============================================================================
STRATEJI_MAP = {
    # --- 🥇 ALTIN (ÇİFT YÖNLÜ) ---
    "ALTIN_TR": { 
        "Sinyal": "GC=F", "Hedef_Kod": "GLDTR.IS", "Hedef_Ad": "QNB Altın BYF (TR)", "Piyasa": "🇹🇷 BIST"
    },
    "ALTIN_US": { 
        "Sinyal": "GC=F", "Hedef_Kod": "GLD",      "Hedef_Ad": "SPDR Gold Shares (ABD)", "Piyasa": "🇺🇸 ABD"
    },

    # --- 🥈 GÜMÜŞ (ÇİFT YÖNLÜ) ---
    "GUMUS_TR": { 
        "Sinyal": "SI=F", "Hedef_Kod": "GMSTR.IS", "Hedef_Ad": "QNB Gümüş BYF (TR)", "Piyasa": "🇹🇷 BIST"
    },
    "GUMUS_US": { 
        "Sinyal": "SI=F", "Hedef_Kod": "SLV",      "Hedef_Ad": "iShares Silver Trust (ABD)", "Piyasa": "🇺🇸 ABD"
    },

    # --- 🇺🇸 SADECE ABD OLANLAR (TR KARŞILIĞI YOK) ---
    "PETROL_US": { 
        "Sinyal": "CL=F", "Hedef_Kod": "USO", "Hedef_Ad": "US Oil Fund", "Piyasa": "🇺🇸 ABD"
    },
    "DOGALGAZ_US": { 
        "Sinyal": "NG=F", "Hedef_Kod": "UNG", "Hedef_Ad": "US Natural Gas Fund", "Piyasa": "🇺🇸 ABD"
    },
    "BAKIR_US": { 
        "Sinyal": "HG=F", "Hedef_Kod": "CPER", "Hedef_Ad": "US Copper Index", "Piyasa": "🇺🇸 ABD"
    },
    "MISIR_US": { 
        "Sinyal": "ZC=F", "Hedef_Kod": "CORN", "Hedef_Ad": "Teucrium Corn Fund", "Piyasa": "🇺🇸 ABD"
    },
    "BUGDAY_US": { 
        "Sinyal": "ZW=F", "Hedef_Kod": "WEAT", "Hedef_Ad": "Teucrium Wheat Fund", "Piyasa": "🇺🇸 ABD"
    }
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
    Yahoo Finance'den fiyat ve piyasa durumunu çeker.
    GitHub'da güvenilir çalışması için period='5d' kullanıyoruz.
    """
    try:
        ticker = yf.Ticker(sembol)
        # Veri yok hatasını aşmak için 5 günlük veri çekiyoruz
        hist = ticker.history(period="5d")
        
        if hist.empty:
            return None, 0.0, "⚪", "VERİ YOK"

        fiyat = hist['Close'].iloc[-1]
        
        # Günlük Değişimi Hesapla
        if len(hist) >= 2:
            onceki_kapanis = hist['Close'].iloc[-2]
            gunluk_degisim = ((fiyat - onceki_kapanis) / onceki_kapanis) * 100
        else:
            gunluk_degisim = 0.0

        # Piyasa durumu (Basit kontrol)
        # Bu kısım GitHub'da bazen yavaşlatabilir, basitleştirdik.
        metin = "AKTİF"
        ikon = "🟢"
            
        return fiyat, gunluk_degisim, ikon, metin

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
    print("🌍 Bot Başlatıldı (GitHub Modu - 1:1 Strateji)...")
    
    hafiza = hafiza_yukle()
    yeni_hafiza = hafiza.copy()
    degisiklik_var_mi = False
    su_an = time.time()

    # Strateji haritasını dönüyoruz
    for strateji_adi, detay in STRATEJI_MAP.items():
        
        # 1. ADIM: SİNYAL (FUTURES) VERİSİNİ ÇEK
        sinyal_kodu = detay["Sinyal"]
        guncel_sinyal_fiyat, sinyal_gunluk_degisim, sinyal_ikon, _ = piyasa_verisi_al(sinyal_kodu)
        
        if guncel_sinyal_fiyat is None: 
            continue

        # Hafızada bu sinyalin (örn GC=F) eski fiyatı var mı?
        eski_veri = hafiza.get(sinyal_kodu, {})
        eski_sinyal_fiyat = eski_veri.get("son_fiyat")

        # 😈 HİLE MODU: İlk kez görüyorsak %5 düşükmüş gibi davran
        if eski_sinyal_fiyat is None:
            eski_sinyal_fiyat = guncel_sinyal_fiyat * 0.95 
            print(f"😈 İlk Tanışma Hilesi Devrede: {sinyal_kodu} -> {strateji_adi}")

        # Hareket Hesapla (Botun gördüğü son fiyata göre)
        degisim_yuzdesi = ((guncel_sinyal_fiyat - eski_sinyal_fiyat) / eski_sinyal_fiyat) * 100
        
        # Ekrana log bas (GitHub loglarında görmek için)
        if abs(degisim_yuzdesi) > 0.1:
            print(f"🔍 {strateji_adi} ({sinyal_kodu}): %{degisim_yuzdesi:.2f}")

        # 🔥 HAREKET EŞİĞİ GEÇİLDİ Mİ?
        if abs(degisim_yuzdesi) >= ESIK_DEGERI:
            
            # 2. ADIM: HEDEF (ETF/BYF) VERİSİNİ ÇEK
            hedef_kodu = detay["Hedef_Kod"]
            hedef_fiyat, hedef_gunluk_degisim, hedef_ikon, hedef_durum = piyasa_verisi_al(hedef_kodu)
            hedef_rsi = rsi_hesapla(hedef_kodu)
            
            # AI Paketini Hazırla
            paket = {
                "tur": "ARBITRAJ", 
                "emtia_adi": detay['Hedef_Ad'],
                "sembol": hedef_kodu,
                "global_degisim": round(degisim_yuzdesi, 2),
                "hedef_fiyat": round(hedef_fiyat, 2) if hedef_fiyat else "Veri Yok",
                "hedef_rsi": round(hedef_rsi, 0),
                "soru": f"Global sinyal ({sinyal_kodu}) %{degisim_yuzdesi:.2f} hareket etti. {detay['Piyasa']} piyasasındaki {detay['Hedef_Ad']} ({hedef_kodu}) için fırsat var mı?"
            }
            
            try: ai_sonuc = ai.yorumla(paket)
            except: ai_sonuc = ".."

            baslik_ikon = "🚀 FIRSAT" if degisim_yuzdesi > 0 else "🔻 DİKKAT"
            
            # Mesajı Oluştur
            mesaj = (
                f"<b>{baslik_ikon}: SİNYAL YAKALANDI!</b>\n"
                f"🌍 <b>Global ({sinyal_kodu}):</b> %{paket['global_degisim']}\n"
                f"------------------------\n"
                f"{detay['Piyasa']} <b>Hedef:</b> {detay['Hedef_Ad']}\n"
                f"🏷️ <b>Kod:</b> {hedef_kodu}\n"
                f"💵 <b>Fiyat:</b> {paket['hedef_fiyat']}\n"
                f"📈 <b>RSI:</b> {paket['hedef_rsi']}\n\n"
                f"🧠 <b>Analiz:</b>\n{ai_yorum}" # Not: ai_brain.py'den gelen değişken adı ai_sonuc
            )
            # Düzeltme: ai_yorum yukarıda ai_sonuc olarak tanımlandı
            mesaj = mesaj.replace("ai_yorum", str(ai_sonuc)) 
            
            bot.gonder(mesaj)
            print(f"✅ MESAJ ATILDI: {strateji_adi}")
            
            # 3. ADIM: SİNYAL FİYATINI GÜNCELLE
            # Dikkat: Aynı sinyali (örn GC=F) kullanan birden fazla strateji olabilir.
            # Hepsi tetiklendikten sonra hafızadaki sinyal fiyatı güncellenmeli.
            yeni_hafiza[sinyal_kodu] = {"son_fiyat": guncel_sinyal_fiyat, "son_mesaj_zamani": su_an}
            degisiklik_var_mi = True
        
        else:
            # Hareket yoksa eski veriyi koru veya ilk kez görüyorsak kaydet
            if eski_sinyal_fiyat is not None:
                # Eğer yeni hafızada zaten güncellenmediyse eskiyi koru
                if sinyal_kodu not in yeni_hafiza: 
                    yeni_hafiza[sinyal_kodu] = eski_veri
            else:
                # İlk görüş (Hile modu çalışsa bile buraya düşebilir)
                yeni_hafiza[sinyal_kodu] = {"son_fiyat": guncel_sinyal_fiyat, "son_mesaj_zamani": su_an}
                degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(yeni_hafiza)
        print("💾 Hafıza güncellendi.")

if __name__ == "__main__":
    main()
