"""매일 시세를 받아 prices.json 으로 저장합니다. 종목은 symbols.txt 에서 관리합니다."""
import json, os, re, datetime
import urllib.request, urllib.parse
import xml.etree.ElementTree as ET
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


# ---------- 내 집 실거래가 (국토교통부) ----------
# GitHub Secrets: MOLIT_KEY(인증키), APT_LAWD(시군구코드 5자리), APT_NAME(단지명), APT_AREA(전용면적), APT_DONG(법정동, 선택)
def apt_deals(key, lawd, ym):
    bases = ["https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
             "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"]
    q = urllib.parse.urlencode({"serviceKey": urllib.parse.unquote(key), "LAWD_CD": lawd,
                                "DEAL_YMD": ym, "pageNo": 1, "numOfRows": 1000})
    err = None
    for b in bases:
        try:
            with urllib.request.urlopen(b + "?" + q, timeout=30) as r:
                root = ET.fromstring(r.read())
            code = (root.findtext(".//resultCode") or "").strip()
            if code not in ("00", "000"):
                err = root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg") or "응답 오류"
                continue
            return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
        except Exception as e:
            err = e
    raise RuntimeError(err)

def fetch_home(old_home):
    key = os.environ.get("MOLIT_KEY", "").strip(); lawd = os.environ.get("APT_LAWD", "").strip()
    name = os.environ.get("APT_NAME", "").strip(); dong = os.environ.get("APT_DONG", "").strip()
    try: area = float(os.environ.get("APT_AREA", "").strip())
    except ValueError: area = 0
    if not (key and lawd and name and area): return old_home
    today = datetime.date.today()
    ch = (old_home or {}).get("checked")
    if ch and (today - datetime.date.fromisoformat(ch)).days < 7: return old_home   # 주 1회만 조회
    norm = lambda t: re.sub(r"\s|단지", "", t)
    nn, deals, (y, m) = norm(name), [], (today.year, today.month)
    for _ in range(24):
        try: rows = apt_deals(key, lawd, f"{y}{m:02d}")
        except Exception as e:
            print("실거래가 조회 실패:", f"{y}{m:02d}", e)
            if not deals: return old_home
            break
        for it in rows:
            try: ar = float(it.get("excluUseAr", "0"))
            except ValueError: continue
            a = norm(it.get("aptNm", ""))
            if abs(ar - area) > 0.3 or not a or not (nn in a or a in nn): continue
            if dong and dong not in it.get("umdNm", ""): continue
            if it.get("cdealType", "").strip().upper() == "O": continue          # 취소된 거래 제외
            try: d = datetime.date(int(it["dealYear"]), int(it["dealMonth"]), int(it["dealDay"])); amt = int(it["dealAmount"].replace(",", "")) * 10000
            except (KeyError, ValueError): continue
            deals.append((d, amt))
        if len(deals) >= 3: break
        m -= 1
        if m == 0: y, m = y - 1, 12
    if not deals:
        print("최근 24개월 내 일치하는 거래가 없습니다."); return old_home
    deals.sort(reverse=True); top = deals[:3]
    print("실거래가 일치 거래", len(deals), "건, 최근", top[0][0])
    return {"price": round(sum(a for _, a in top) / len(top)), "last": top[0][1], "date": top[0][0].isoformat(),
            "n": len(top), "checked": today.isoformat()}

home = fetch_home(old.get("re", {}).get("home"))

out = {"updated": datetime.date.today().isoformat(), "fx": fx, "items": items}
if home: out["re"] = {"home": home}
json.dump(out, open("prices.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("완료", len(items), "종목")
