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
SPAM_SURESI = 14400 # 4 Saat

# ==============================================================================
# ⚡ ANLIK VERİ HARİTASI (FOREX & SPOT MODU)
# ==============================================================================
# Gecikmeli Vadeli kodlarını (GC=F), Anlık Spot kodlarıyla (XAUUSD=X) değiştirdik.
STRATEJI_MAP = {
    # --- 🥇 DEĞERLİ METALLER (ANLIK) ---
    "XAUUSD=X": {"Ad": "Altın (Ons)",   "ETF": "GLD"},  # Spot Altın
    "XAGUSD=X": {"Ad": "Gümüş (Ons)",   "ETF": "SLV"},  # Spot Gümüş
    "XPTUSD=X": {"Ad": "Platin",        "ETF": "PPLT"}, # Spot Platin
    "XPDUSD=X": {"Ad": "Paladyum",      "ETF": "PALL"}, # Spot Paladyum

    # --- 🛢️ ENERJİ & ENDÜSTRİ (EN HIZLI VADELİLER) ---
    # Enerji için Forex kodu yoktur, en hızlı vadeli kontratı kullanıyoruz
    "CL=F":     {"Ad": "Petrol (WTI)",  "ETF": "USO"},
    "NG=F":     {"Ad": "Doğalgaz",      "ETF": "UNG"},
    "HG=F":     {"Ad": "Bakır",         "ETF": "CPER"},
    "NI=F":     {"Ad": "Nikel",         "ETF": "NIKL"},

    # --- 🌾 TARIM ---
    "ZW=F":     {"Ad": "Buğday",        "ETF": "WEAT"},
    "ZC=F":     {"Ad": "Mısır",         "ETF": "CORN"}
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

def veri_getir(sembol):
    """
    Veriyi '1 Dakikalık' (interval='1m') periyotta çekerek
    gecikmeyi minimuma indirir ve anlık fiyatı yakalar.
    """
    try:
        ticker = yf.Ticker(sembol)
        
        # ⚡ SİHİRLİ DOKUNUŞ: 1 Dakikalık veri iste
        hist = ticker.history(period="1d", interval="1m")
        
        # Eğer piyasa kapalıysa veya 1dk veri yoksa (hafta sonu vb.) normal 5 günlüğe dön
        if len(hist) == 0:
            hist = ticker.history(period="5d")
        
        if len(hist) < 2: return None
        
        guncel = hist['Close'].iloc[-1]
        
        # Değişimi hesaplarken, günün açılışına veya önceki kapanışa göre hesapla
        # Bu sayede anlık değişim daha doğru görünür
        onceki_kapanis = ticker.info.get('previousClose')
        # Eğer bilgi gelmezse tablodaki ilk veriyi al
        if onceki_kapanis is None: 
            onceki_kapanis = hist['Close'].iloc[0]

        degisim = ((guncel - onceki_kapanis) / onceki_kapanis) * 100
        
        # RSI Hesabı
        if len(hist) > 14:
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            rsi_val = rsi.iloc[-1]
        else:
            rsi_val = 50

        return {"fiyat": guncel, "degisim": degisim, "rsi": rsi_val}
    except: return None

def main():
    print("🌍 GitHub Action Başlatıldı (Anlık Mod)...")
    
    son_bildirimler = hafiza_yukle()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        # Kaynak verisini çek (Artık Forex/Spot olduğu için çok hızlı)
        kaynak_veri = veri_getir(kaynak_kodu)
        
        # Hareket yoksa geç (%0.5)
        if not kaynak_veri or abs(kaynak_veri["degisim"]) < 0.5: continue

        etf_kodu = detay["ETF"]
        etf_veri = veri_getir(etf_kodu)
        if not etf_veri: continue

        # Fırsat Analizi (Makas)
        if abs(kaynak_veri["degisim"]) > 0.8:
            
            # SPAM KONTROLÜ
            if etf_kodu in son_bildirimler:
                son_zaman = son_bildirimler[etf_kodu]
                if (su_an - son_zaman) < SPAM_SURESI:
                    print(f"🛑 {etf_kodu} için zaten mesaj atıldı. Pas geçiliyor.")
                    continue

            # Yeni Sinyal İşleme
            paket = {
                "tur": "HISSE", 
                "emtia_adi": f"{detay['Ad']} (Anlık)", # İsim güncellendi
                "sembol": etf_kodu,
                "emtia_degisim": round(kaynak_veri["degisim"], 2),
                "hisse_degisim": round(etf_veri["degisim"], 2),
                "fiyat": round(etf_veri["fiyat"], 2),
                "rsi": round(etf_veri["rsi"], 0),
                "trend": "YÜKSELİŞ" if etf_veri["degisim"] > 0 else "DÜŞÜŞ"
            }
            
            ai_sonuc = ai.yorumla(paket)
            
            baslik_ikon = "⚡ ANLIK SİNYAL" # İkon değişti
            if "GÜÇLÜ AL" in ai_sonuc.upper(): baslik_ikon = "🚨 GÜÇLÜ SİNYAL"
            
            mesaj = (
                f"<b>{baslik_ikon}: {detay['Ad']} -> {etf_kodu}</b>\n\n"
                f"⏱️ <b>Kaynak (Canlı):</b> %{paket['emtia_degisim']}\n"
                f"💰 <b>Hedef (ETF):</b> %{paket['hisse_degisim']}\n"
                f"💵 <b>Fiyat:</b> {paket['fiyat']}$\n"
                f"------------------------\n"
                f"📈 <b>RSI:</b> {paket['rsi']:.0f}\n"
                f"🤖 <b>AI YORUMU:</b>\n{ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ Mesaj atıldı: {etf_kodu}")
            
            son_bildirimler[etf_kodu] = su_an
            degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(son_bildirimler)
        print("💾 Hafıza dosyası güncellendi.")
    else:
        print("💤 Yeni sinyal yok, hafıza değişmedi.")

if __name__ == "__main__":
    main()
