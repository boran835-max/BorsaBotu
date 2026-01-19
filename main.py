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
SPAM_SURESI = 14400 # 4 Saat (Mesaj attıktan sonra 4 saat susar)

# ==============================================================================
# 🛡️ FİNAL TAM LİSTE (NİKEL DAHİL)
# ==============================================================================
STRATEJI_MAP = {
    # --- 🥇 DEĞERLİ METALLER ---
    "GC=F": {"Ad": "Altın",      "ETF": "GLD"},
    "SI=F": {"Ad": "Gümüş",      "ETF": "SLV"},
    "PL=F": {"Ad": "Platin",     "ETF": "PPLT"},
    "PA=F": {"Ad": "Paladyum",   "ETF": "PALL"},

    # --- 🏗️ ENDÜSTRİYEL ---
    "HG=F": {"Ad": "Bakır",      "ETF": "CPER"},
    "NI=F": {"Ad": "Nikel",      "ETF": "NIKL"}, 

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
        # Hata almamak için 5 günlük standart veri çekiyoruz
        hist = ticker.history(period="5d")
        
        if len(hist) < 2: return None
        
        guncel = hist['Close'].iloc[-1]
        onceki = hist['Close'].iloc[-2]
        degisim = ((guncel - onceki) / onceki) * 100
        
        # RSI Hesabı
        if len(hist) > 14:
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            rsi_val = rsi.iloc[-1]
        else: rsi_val = 50

        return {"fiyat": guncel, "degisim": degisim, "rsi": rsi_val}
    except: return None

def main():
    print("🌍 Bot Başlatıldı (Hafıza Sıfırlandı, Oto-Kontrol Açık)...")
    
    # Hafıza dosyasını yüklemeye çalışır, yoksa boş başlar (Sıfırladığımız için boş başlayacak)
    son_bildirimler = hafiza_yukle()
    degisiklik_var_mi = False
    su_an = time.time()

    for kaynak_kodu, detay in STRATEJI_MAP.items():
        kaynak_veri = veri_getir(kaynak_kodu)
        if not kaynak_veri: continue
        
        # FİLTRE: %0.8 altındaki hareketleri önemseme
        if abs(kaynak_veri["degisim"]) < 0.8: 
            continue

        etf_kodu = detay["ETF"]
        etf_veri = veri_getir(etf_kodu)
        if not etf_veri: continue

        # --- OTO KONTROL (SPAM KORUMASI) ---
        # Bot hafızaya bakar. Eğer 'hafiza.json' silindiği için liste boşsa
        # burayı pas geçer ve mesajı GÖNDERİR.
        if etf_kodu in son_bildirimler:
            son_zaman = son_bildirimler[etf_kodu]
            if (su_an - son_zaman) < SPAM_SURESI:
                print(f"🛑 {etf_kodu} mesajı yakın zamanda atıldı. Pas geçiliyor.")
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
        print(f"✅ MESAJ GÖNDERİLDİ: {etf_kodu}")
        
        # Hafızaya kaydet ki 4 saat boyunca bir daha atmasın
        son_bildirimler[etf_kodu] = su_an
        degisiklik_var_mi = True

    if degisiklik_var_mi:
        hafiza_kaydet(son_bildirimler)
        print("💾 Yeni hafıza dosyası oluşturuldu.")
    else:
        print("💤 Hareket yok (%0.8 altı), mesaj atılmadı.")

if __name__ == "__main__":
    main()
