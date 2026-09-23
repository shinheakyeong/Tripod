"""
트라이팟 35년 백테스트 재현
  python3 backtest.py                  # data/market.csv 로 실행
  python3 backtest.py --start 20100211 # 기간 지정 (TQQQ 상장 이후 등)

가상 ETF 합성 (나스닥100 가격지수 기반)
  일수익 = L × (지수수익 + 배당/252) − (L−1) × (T-bill + 스프레드)/252 − 보수/252
  현금   = (T-bill − 헤어컷)/252
체결: T일 종가 신호 → T+1일 종가 체결 → T+2일 수익부터 새 배분 반영
"""
import argparse, math
from tripod import evaluate, load_csv, ALLOC, gear

COST = dict(exp={"QQQ": 0.20, "QLD": 0.95, "TQQQ": 0.95},   # 운용보수 %/년
            lev={"QQQ": 1, "QLD": 2, "TQQQ": 3},
            spread=0.5, cash_haircut=0.3, div=0.45, trade_bps=3.0, lag=2)


def asset_returns(r_idx, irx):
    rf = irx / 100 / 252
    out = {}
    for k, L in COST["lev"].items():
        out[k] = (L * (r_idx + COST["div"]/100/252)
                  - (L - 1) * (rf + COST["spread"]/100/252)
                  - COST["exp"][k]/100/252)
    out["CASH"] = max(irx - COST["cash_haircut"], 0) / 100 / 252
    return out


def stats(eq, dates, rets):
    yrs = len(rets) / 252
    cagr = eq[-1] ** (1/yrs) - 1
    peak, mdd, sq = eq[0], 0.0, 0.0
    for v in eq:
        peak = max(peak, v); d = v/peak - 1
        mdd = min(mdd, d); sq += (d*100) ** 2
    ulcer = math.sqrt(sq / len(eq))
    down = [min(x, 0) for x in rets]
    dd_dev = math.sqrt(sum(x*x for x in down)/len(down)) * math.sqrt(252)
    sortino = cagr / dd_dev if dd_dev else float("nan")
    return cagr, mdd, ulcer, sortino


def run(rows, start, end):
    evaluate(rows)
    irx = None
    for r in rows:                      # T-bill 결측 → 직전값 유지
        irx = r["irx"] if r.get("irx") is not None else irx
        r["irx_f"] = irx if irx is not None else 0.0

    idx = [i for i, r in enumerate(rows) if start <= r["date"] <= end]
    strat, bh = [1.0], {k: [1.0] for k in ("QQQ", "QLD", "TQQQ")}
    s_rets, bh_rets = [], {k: [] for k in bh}
    trades, prev_hold = [], None
    for i in idx[1:]:
        sig = rows[i - COST["lag"]]["state"]        # T+2일 수익에 적용되는 신호
        if sig is None:
            continue
        hold = ALLOC[sig]
        ar = asset_returns(rows[i]["ndx"]/rows[i-1]["ndx"] - 1, rows[i-1]["irx_f"])
        r = sum(w * ar[k] for k, w in hold.items())
        if prev_hold is not None and hold != prev_hold:
            turnover = sum(abs(hold.get(k, 0) - prev_hold.get(k, 0))
                           for k in set(hold) | set(prev_hold)) / 2
            r -= turnover * COST["trade_bps"] / 1e4
            trades.append(rows[i-1]["date"])      # 체결일(T+1)
        prev_hold = hold
        s_rets.append(r); strat.append(strat[-1] * (1 + r))
        for k in bh:
            bh_rets[k].append(ar[k]); bh[k].append(bh[k][-1] * (1 + ar[k]))
    return strat, s_rets, bh, bh_rets, trades


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/market.csv")
    ap.add_argument("--start", default="19910101")
    ap.add_argument("--end", default="20260904")
    a = ap.parse_args()
    rows = load_csv(a.csv)
    strat, s_rets, bh, bh_rets, trades = run(rows, a.start, a.end)
    yrs = len(s_rets) / 252
    print(f"기간 {a.start} ~ {a.end}  ({yrs:.1f}년)\n")
    print(f"{'':12}{'CAGR':>8}{'MDD':>9}{'Ulcer':>8}{'Sortino':>9}")
    for name, eq, rr in [("트라이팟", strat, s_rets)] + \
                        [(f"{k} 보유", bh[k], bh_rets[k]) for k in bh]:
        c, m, u, s = stats(eq, None, rr)
        print(f"{name:12}{c*100:7.1f}%{m*100:8.1f}%{u:8.1f}{s:9.2f}")
    print(f"\n총 매매 {len(trades)}회 · 연평균 {len(trades)/yrs:.1f}회")
    print(f"최근 매매일(체결): {', '.join(trades[-5:])}")
