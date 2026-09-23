"""
트라이팟(Tripod) 규칙 엔진 + 시세 수집
- 규칙 출처: 유튜브 '송팀장' 채널 공개 규칙 (2026-08 영상 기준값)
- 파이썬 표준 라이브러리만 사용 (설치 불필요, Python 3.9+)
"""
import csv, io, json, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ───────── 규칙 파라미터 (원본값) ─────────
P = dict(
    sma_window=250,        # 다리1: 나스닥100 250일 이동평균
    band_up=0.01,          #   지수 > 250일선 × 1.01 → 상승
    band_down=-0.05,       #   지수 < 250일선 × 0.95 → 하락 (사이면 직전 유지)
    vix_window=10,         # 다리2: VIX 10일 평균
    vix_up=28.0,           #   상승장 위험회피 문턱
    vix_down=18.0,         #   하락장 공포 문턱
    dd_window=252,         # 다리3: 52주(252거래일) 고점 대비 낙폭
    dd_threshold=-0.09,    #   낙폭 9% 초과 → 위험회피
)
ALLOC = {
    "UP_RISKON":  {"TQQQ": 1.0},
    "UP_RISKOFF": {"QQQ": 0.5, "QLD": 0.5},
    "DOWN_CALM":  {"QQQ": 0.5, "QLD": 0.5},
    "DOWN_FEAR":  {"CASH": 1.0},
}
LABEL = {"UP_RISKON": "상승·위험선호", "UP_RISKOFF": "상승·위험회피",
         "DOWN_CALM": "하락·안정", "DOWN_FEAR": "하락·공포"}
GEAR = {"TQQQ": 3.0, "QLD": 2.0, "QQQ": 1.0, "CASH": 0.0}


def alloc_text(state):
    a = ALLOC[state]
    return " + ".join(f"{k} {int(v*100)}%" for k, v in a.items())


def gear(state):
    return sum(GEAR[k] * v for k, v in ALLOC[state].items())


# ───────── 지표 계산 · 판정 ─────────
def evaluate(rows, p=P):
    """rows: [{'date','ndx','vix'}] 오름차순. 각 행에 지표와 state를 채운다."""
    ndx = [r["ndx"] for r in rows]
    vix = [r["vix"] for r in rows]
    regime = None
    for i, r in enumerate(rows):
        r["sma"] = sum(ndx[i-p["sma_window"]+1:i+1]) / p["sma_window"] if i >= p["sma_window"]-1 else None
        w = [v for v in vix[max(0, i-p["vix_window"]+1):i+1] if v is not None]
        r["vix_ma"] = sum(w)/len(w) if len(w) == p["vix_window"] else None
        if i >= p["dd_window"]-1:
            r["high52"] = max(ndx[i-p["dd_window"]+1:i+1]); r["dd"] = r["ndx"]/r["high52"]-1
        else:
            r["high52"] = r["dd"] = None
        r["gap"] = r["ndx"]/r["sma"]-1 if r["sma"] else None
        r["state"] = None
        if r["gap"] is None:
            continue
        if r["gap"] > p["band_up"]:
            regime = "UP"
        elif r["gap"] < p["band_down"]:
            regime = "DOWN"
        if regime is None or r["vix_ma"] is None or r["dd"] is None:
            continue
        if regime == "UP":
            ok = r["vix_ma"] < p["vix_up"] and r["dd"] >= p["dd_threshold"]
            r["state"] = "UP_RISKON" if ok else "UP_RISKOFF"
        else:
            r["state"] = "DOWN_CALM" if r["vix_ma"] < p["vix_down"] else "DOWN_FEAR"
    return rows


# ───────── 시세 수집 ─────────
UA = {"User-Agent": "Mozilla/5.0 (tripod-signal)"}
NY = ZoneInfo("America/New_York")


def _get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as f:
        return f.read().decode()


def yahoo(symbol):
    """Yahoo chart API 일간 종가 → {YYYYMMDD: close}. 장중 미완성 봉은 제외."""
    last_err = None
    for host in ("query1", "query2"):
        try:
            url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
                   f"?period1=0&period2=9999999999&interval=1d&includePrePost=false")
            res = json.loads(_get(url))["chart"]["result"][0]
            ts, closes = res["timestamp"], res["indicators"]["quote"][0]["close"]
            out = {}
            for t, c in zip(ts, closes):
                if c is not None:
                    out[datetime.fromtimestamp(t, NY).strftime("%Y%m%d")] = float(c)
            # 미국 장이 아직 안 끝났으면 오늘 봉 제거 (16:00 ET 이후만 확정)
            now = datetime.now(NY)
            today = now.strftime("%Y%m%d")
            if today in out and now.hour < 16:
                out.pop(today)
            return out
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Yahoo {symbol} 수집 실패: {last_err}")


def fred_ndx():
    """FRED NASDAQ100 (교차검증용) → {YYYYMMDD: close}"""
    txt = _get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100")
    out = {}
    for r in csv.reader(io.StringIO(txt)):
        if len(r) == 2 and r[1] not in ("", ".") and r[0][:1].isdigit():
            out[r[0].replace("-", "")] = float(r[1])
    return out


def load_live():
    """나스닥100·VIX 전체 이력을 받아 rows로 합친다."""
    ndx, vix = yahoo("%5ENDX"), yahoo("%5EVIX")
    rows = [{"date": d, "ndx": ndx[d], "vix": vix.get(d)} for d in sorted(ndx)]
    return rows


def load_csv(path):
    rows = []
    for r in csv.DictReader(open(path)):
        rows.append({"date": r["date"], "ndx": float(r["ndx"]),
                     "vix": float(r["vix"]) if r.get("vix") else None,
                     "irx": float(r["irx"]) if r.get("irx") else None})
    return rows
