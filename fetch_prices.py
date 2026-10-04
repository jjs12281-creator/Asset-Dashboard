"""매일 시세를 받아 prices.json 으로 저장합니다. 종목은 symbols.txt 에서 관리합니다."""
import json, os, datetime
import urllib.request
import yfinance as yf

SYMBOLS = {}
for line in open("symbols.txt", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#"):
        code, _, name = line.partition(" ")
        SYMBOLS[code.strip()] = name.strip() or code.strip()

old = {}
if os.path.exists("prices.json"):
    try: old = json.load(open("prices.json", encoding="utf-8"))
    except Exception: old = {}

def upbit(sym):
    """업비트 원화 시세 (KRW-BTC 형식). 공개 API라 키가 필요 없습니다."""
    with urllib.request.urlopen("https://api.upbit.com/v1/ticker?markets=" + sym, timeout=15) as r:
        d = json.load(r)[0]
    return float(d["trade_price"]), float(d["prev_closing_price"])

def last_two(sym):
    h = yf.Ticker(sym).history(period="7d")["Close"].dropna()
    if len(h) == 0: raise ValueError("no data")
    return float(h.iloc[-1]), float(h.iloc[-2]) if len(h) > 1 else float(h.iloc[-1])

items = {}
for sym, name in SYMBOLS.items():
    cur = "KRW" if sym.endswith((".KS", ".KQ")) or sym.startswith("KRW-") else "USD"
    try:
        p, prev = upbit(sym) if sym.startswith("KRW-") else last_two(sym)
        items[sym] = {"name": name, "price": round(p, 4), "prev": round(prev, 4), "cur": cur}
    except Exception as e:
        print("실패(이전 값 유지):", sym, e)
        if sym in old.get("items", {}): items[sym] = old["items"][sym]

try: fx = round(last_two("KRW=X")[0], 2)
except Exception as e:
    print("환율 실패(이전 값 유지):", e); fx = old.get("fx", 1400)

json.dump({"updated": datetime.date.today().isoformat(), "fx": fx, "items": items},
          open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("완료", len(items), "종목")
