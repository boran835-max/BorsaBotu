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
# 🛡️ TAM KADRO STRATEJİ LİSTESİ (VADELİ -> ETF)
# ==============================================================================
# Yahoo'nun engellemediği VADELİ kodları kullanıyoruz. (GC=F, NI=F vb.)
STRATEJI_MAP = {
    # --- 🥇 DEĞERLİ METALLER ---
    "GC=F": {"Ad": "Altın",      "ETF": "GLD"},
    "SI=F": {"Ad": "Gümüş",      "ETF": "SLV"},
    "PL=F": {"Ad": "Platin",     "ETF": "PPLT"},
    "PA=F": {"Ad": "Paladyum",   "ETF": "PALL"},

    # --- 🏗️ ENDÜSTRİYEL METALLER (NİKEL BURADA!) ---
    "HG=F": {"Ad": "Bakır",      "ETF": "CPER"},
    "NI=F": {"Ad": "Nikel",      "ETF": "NIKL"},  # <-- İŞTE BURADA, EKSİKSİZ!
    "ALI=F": {"Ad": "Alüminyum", "ETF": "JJU"},   # Alüminyumu da ekledim.

    # --- 🛢️ ENERJİ ---
    "CL=F": {"Ad": "Petrol (WTI)", "ETF": "USO"},
    "NG=F": {"Ad": "Doğalgaz",     "ETF": "UNG"},

    # --- 🌾 TARIM ---
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

def veri_getir(sembol):
    try:
        ticker = yf.Ticker(sembol)
        # 1 dakikalık veri yerine 5 günlük standart veri (Daha güvenli, hata vermez)
        hist = ticker.history(period="5d")
        
        if len(hist) < 2: return None
        
        guncel = hist['Close'].iloc[-1]
        onceki = hist['Close'].iloc[-2]
        
        # Değişim Hesabı
        degisim = ((guncel - onceki) / onceki) * 100
        
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
    print("🌍 GitHub Bot Başlatıldı (Tam Liste)...")
    
    son_bildirimler = hafiza_yukle()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        # Kaynak verisini çek
        kaynak_veri = veri_getir(kaynak_kodu)
        
        if not kaynak_veri:
            # Nikel bazen veri vermezse boşuna beklemesin diye log düşüyoruz
            # print(f"⚠️ Veri yok: {kaynak_kodu}") 
            continue
        
        # Eğer hareket %0.8'den küçükse pas geç (Filtre burada)
        if abs(kaynak_veri["degisim"]) < 0.8: 
            continue

        etf_kodu = detay["ETF"]
        etf_veri = veri_getir(etf_kodu)
        if not etf_veri: continue

        # SPAM KONTROLÜ
        if etf_kodu in son_bildirimler:
            son_zaman = son_bildirimler[etf_kodu]
            if (su_an - son_zaman) < SPAM_SURESI:
                print(f"🛑 {etf_kodu} için zaten mesaj atıldı.")
                continue

        # AI Paketi
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
        
        try:
            ai_sonuc = ai.yorumla(paket)
        except:
            ai_sonuc = "AI Yorumu Alınamadı"
        
        baslik_ikon = "🔔 SİNYAL"
        if "GÜÇLÜ AL" in str(ai_sonuc).upper(): baslik_ikon = "🚨 GÜÇLÜ SİNYAL"
        
        mesaj = (
            f"<b>{baslik_ikon}: {detay['Ad']} -> {etf_kodu}</b>\n\n"
            f"📊 <b>Vadeli:</b> %{paket['emtia_degisim']}\n"
            f"💰 <b>ETF:</b> %{paket['hisse_degisim']}\n"
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
        print("💤 Yeni sinyal yok, piyasa sakin.")

if __name__ == "__main__":
    main()
