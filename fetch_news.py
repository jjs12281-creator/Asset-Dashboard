"""보유 종목·부동산 뉴스 헤드라인을 모아 AI로 요약해 news.json 으로 저장합니다.
필요한 Secrets: GEMINI_API_KEY 또는 ANTHROPIC_API_KEY (둘 중 하나, 없으면 헤드라인 링크만 저장)
선택: NEWS_PASS(내 부동산 뉴스 암호화 비밀번호), APT_NAME(내 단지명), APT_REGION(예: 수원 팔달구)
"""
import os, re, json, time, base64, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

def load_symbols():
    out = {}
    for line in open("symbols.txt", encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#"):
            code, _, name = line.partition(" ")
            out[code.strip()] = name.strip() or code.strip()
    return out

def gnews(q, n=6, days=3):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": f"{q} when:{days}d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        root = ET.fromstring(r.read())
    res = []
    for it in root.iter("item"):
        d = ""
        try: d = parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception: pass
        res.append({"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                    "source": (it.findtext("source") or "").strip(), "date": d})
        if len(res) >= n: break
    return res

def ask_json(prompt):
    gk = os.environ.get("GEMINI_API_KEY", "").strip(); ak = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if gk:
        model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            json.dumps(body).encode(), {"Content-Type": "application/json", "x-goog-api-key": gk})
        txt = json.load(urllib.request.urlopen(req, timeout=120))["candidates"][0]["content"]["parts"][0]["text"]
    elif ak:
        body = {"model": (os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001"), "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps(body).encode(),
            {"x-api-key": ak, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        txt = json.load(urllib.request.urlopen(req, timeout=120))["content"][0]["text"]
    else:
        return None
    return json.loads(re.search(r"\{.*\}", txt, re.S).group(0))

RULE = ("헤드라인에 나온 사실만 근거로 한국어로 정리해라. 헤드라인에 없는 내용은 추측해서 쓰지 마라. "
        "매수·매도를 지시하지 말고, 근거가 부족하면 mood를 '정보부족'으로 해라. mood는 긍정|중립|부정|정보부족 중 하나. JSON만 출력해라.")

def summarize_stocks(data):
    p = (RULE + '\n출력 형식: {"종목코드": {"mood": "", "summary": "2~3문장", "pos": ["긍정 요인"], "neg": ["부정 요인·리스크"], "watch": ["확인할 일정·지표"]}}\n[데이터]\n'
         + json.dumps(data, ensure_ascii=False))
    return ask_json(p)

def summarize_topic(label, heads):
    p = (RULE + f'\n주제: {label}\n출력 형식: {{"mood": "", "summary": "3~4문장", "points": ["핵심 포인트 3~5개"]}}\n[헤드라인]\n'
         + json.dumps(heads, ensure_ascii=False))
    return ask_json(p)

def encrypt(obj, pw):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    salt, iv, it = os.urandom(16), os.urandom(12), 200000
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=it).derive(pw.encode())
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"salt": b(salt), "iv": b(iv), "iter": it, "ct": b(ct)}

def safe(fn, *a, default=None):
    try: return fn(*a)
    except Exception as e:
        print("실패:", getattr(fn, "__name__", "fn"), type(e).__name__, str(e)[:120]); return default

def main():
    old = {}
    if os.path.exists("news.json"):
        try: old = json.load(open("news.json", encoding="utf-8"))
        except Exception: old = {}
    syms = load_symbols(); has_ai = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
    heads = {}
    for code, name in syms.items():
        q = name + (" 주가" if not code.startswith("KRW-") else "")
        h = safe(gnews, q, 6, default=None)
        if h is not None: heads[code] = h
        time.sleep(1)
    stocks = dict(old.get("stocks", {}))
    ai = safe(summarize_stocks, {c: {"name": syms[c], "headlines": [x["title"] for x in hs]} for c, hs in heads.items()}) if has_ai and heads else None
    for c, hs in heads.items():
        e = {"name": syms[c], "links": hs}
        if ai and isinstance(ai.get(c), dict): e.update({k: ai[c].get(k) for k in ("mood", "summary", "pos", "neg", "watch")})
        elif c in stocks: e.update({k: stocks[c].get(k) for k in ("mood", "summary", "pos", "neg", "watch")})
        stocks[c] = e
    stocks = {c: v for c, v in stocks.items() if c in syms}

    mh, seen = [], set()
    for q in ("부동산 시장 아파트 매매", "아파트값 전망 금리", "부동산 정책 대출 규제"):
        for x in safe(gnews, q, 5, 3, default=[]) or []:
            if x["title"] not in seen: seen.add(x["title"]); mh.append(x)
        time.sleep(1)
    market = old.get("market")
    if mh:
        market = {"links": mh[:8]}
        r = safe(summarize_topic, "국내 부동산 시장 최신 동향", [x["title"] for x in mh]) if has_ai else None
        if r: market.update({k: r.get(k) for k in ("mood", "summary", "points")})

    private = None; pw = os.environ.get("NEWS_PASS", "").strip(); apt = os.environ.get("APT_NAME", "").strip(); reg = os.environ.get("APT_REGION", "").strip()
    if apt and pw:
        hh, seen = [], set()
        for q in (apt, f"{reg} 아파트" if reg else None):
            if not q: continue
            for x in safe(gnews, q, 6, 14, default=[]) or []:
                if x["title"] not in seen: seen.add(x["title"]); hh.append(x)
            time.sleep(1)
        if hh:
            home = {"links": hh[:8]}
            r = safe(summarize_topic, f"내가 보유한 아파트({apt}, {reg}) 관련 소식", [x["title"] for x in hh]) if has_ai else None
            if r: home.update({k: r.get(k) for k in ("mood", "summary", "points")})
            private = encrypt({"home": home}, pw)
    elif apt and not pw:
        print("NEWS_PASS가 없어 내 부동산 뉴스는 건너뜀(공개 저장소 노출 방지)")
    out = {"updated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
           "ai": bool(ai) or (has_ai and bool(market and market.get("summary"))), "stocks": stocks}
    if market: out["market"] = market
    if private: out["private"] = private
    elif old.get("private") and not apt: pass
    json.dump(out, open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("완료: 종목", len(stocks), "/ 시장뉴스", len(mh), "/ AI", out["ai"])

if __name__ == "__main__":
    main()
