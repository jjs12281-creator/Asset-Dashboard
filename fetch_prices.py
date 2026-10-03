"""매일 시세를 받아 prices.json 으로 저장합니다. 종목 추가는 아래 SYMBOLS 에 한 줄만 추가하세요."""
import json, os, datetime
import yfinance as yf

# 코드: 표시 이름   (코스피 .KS / 코스닥 .KQ / 미국은 티커 그대로)
SYMBOLS = {
    "000660.KS": "SK하이닉스",
    "005930.KS": "삼성전자",
    "NVDA": "엔비디아",
}

old = {}
if os.path.exists("prices.json"):
    try: old = json.load(open("prices.json", encoding="utf-8"))
    except Exception: old = {}

def last_two(sym):
    h = yf.Ticker(sym).history(period="7d")["Close"].dropna()
    if len(h) == 0: raise ValueError("no data")
    return float(h.iloc[-1]), float(h.iloc[-2]) if len(h) > 1 else float(h.iloc[-1])

items = {}
for sym, name in SYMBOLS.items():
    cur = "KRW" if sym.endswith((".KS", ".KQ")) else "USD"
    try:
        p, prev = last_two(sym)
        items[sym] = {"name": name, "price": round(p, 2), "prev": round(prev, 2), "cur": cur}
    except Exception as e:
        print("실패(이전 값 유지):", sym, e)
        if sym in old.get("items", {}): items[sym] = old["items"][sym]

try: fx = round(last_two("KRW=X")[0], 2)
except Exception as e:
    print("환율 실패(이전 값 유지):", e); fx = old.get("fx", 1400)

json.dump({"updated": datetime.date.today().isoformat(), "fx": fx, "items": items},
          open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("완료", len(items), "종목")
