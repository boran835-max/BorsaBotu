import warnings
warnings.filterwarnings("ignore")

import time
import os
import json # Hafıza dosyası için gerekli
import yfinance as yf
from ai_brain import AITrader
from notifier import TelegramBot

# ==============================================================================
# ⚙️ AYARLAR
# ==============================================================================
HAFIZA_DOSYASI = "hafiza.json"
SPAM_SURESI = 14400 # 4 Saat (Aynı sinyali 4 saat boyunca tekrar atmaz)

STRATEJI_MAP = {
    "GC=F": {"Ad": "Altın",      "ETF": "GLD"},
    "SI=F": {"Ad": "Gümüş",      "ETF": "SLV"},
    "PL=F": {"Ad": "Platin",     "ETF": "PPLT"},
    "PA=F": {"Ad": "Paladyum",   "ETF": "PALL"},
    "HG=F": {"Ad": "Bakır",      "ETF": "CPER"},
    "NI=F": {"Ad": "Nikel",      "ETF": "NIKL"}, 
    "CL=F": {"Ad": "Petrol",     "ETF": "USO"},
    "NG=F": {"Ad": "Doğalgaz",   "ETF": "UNG"},
    "ZW=F": {"Ad": "Buğday",     "ETF": "WEAT"},
    "ZC=F": {"Ad": "Mısır",      "ETF": "CORN"}
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
    try:
        ticker = yf.Ticker(sembol)
        hist = ticker.history(period="5d")
        if len(hist) < 2: return None
        
        guncel = hist['Close'].iloc[-1]
        onceki = hist['Close'].iloc[-2]
        degisim = ((guncel - onceki) / onceki) * 100
        
        # Basit RSI
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
    print("🌍 GitHub Action Başlatıldı...")
    
    # 1. Eski hafızayı yükle
    son_bildirimler = hafiza_yukle()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        # Verileri çek
        kaynak_veri = veri_getir(kaynak_kodu)
        if not kaynak_veri or abs(kaynak_veri["degisim"]) < 0.5: continue

        etf_kodu = detay["ETF"]
        etf_veri = veri_getir(etf_kodu)
        if not etf_veri: continue

        # Fırsat Analizi (Makas)
        if abs(kaynak_veri["degisim"]) > 0.8:
            
            # --- SPAM KONTROLÜ (Kalıcı Hafıza) ---
            # Eğer daha önce mesaj attıysak ve süresi dolmadıysa GEÇ
            if etf_kodu in son_bildirimler:
                son_zaman = son_bildirimler[etf_kodu]
                if (su_an - son_zaman) < SPAM_SURESI:
                    print(f"🛑 {etf_kodu} için zaten mesaj atıldı. Pas geçiliyor.")
                    continue

            # Yeni Sinyal İşleme
            paket = {
                "tur": "HISSE", 
                "emtia_adi": f"{detay['Ad']} (Vadeli)",
                "sembol": etf_kodu,
                "emtia_degisim": round(kaynak_veri["degisim"], 2),
                "hisse_degisim": round(etf_veri["degisim"], 2),
                "fiyat": round(etf_veri["fiyat"], 2),
                "rsi": round(etf_veri["rsi"], 0),
                "trend": "YÜKSELİŞ" if etf_veri["degisim"] > 0 else "DÜŞÜŞ"
            }
            
            ai_sonuc = ai.yorumla(paket)
            
            baslik_ikon = "🔔 SİNYAL"
            if "GÜÇLÜ AL" in ai_sonuc.upper(): baslik_ikon = "🚨 GÜÇLÜ SİNYAL"
            
            mesaj = (
                f"<b>{baslik_ikon}: {detay['Ad']} -> {etf_kodu}</b>\n\n"
                f"📊 <b>Kaynak:</b> %{paket['emtia_degisim']}\n"
                f"💰 <b>ETF:</b> %{paket['hisse_degisim']}\n"
                f"💵 <b>Fiyat:</b> {paket['fiyat']}$\n"
                f"------------------------\n"
                f"📈 <b>RSI:</b> {paket['rsi']:.0f}\n"
                f"🤖 <b>AI YORUMU:</b>\n{ai_sonuc}"
            )
            
            bot.gonder(mesaj)
            print(f"✅ Mesaj atıldı: {etf_kodu}")
            
            # Hafızayı Güncelle
            son_bildirimler[etf_kodu] = su_an
            degisiklik_var_mi = True

    # 2. İşlem bitince hafızayı dosyaya kaydet
    if degisiklik_var_mi:
        hafiza_kaydet(son_bildirimler)
        print("💾 Hafıza dosyası güncellendi.")
    else:
        print("💤 Yeni sinyal yok, hafıza değişmedi.")

if __name__ == "__main__":
    main()