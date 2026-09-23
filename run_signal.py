"""
트라이팟 일일 신호 알림
- 매 거래일 미국 장 마감 후 실행 (GitHub Actions: 한국시간 화~토 07:30)
- 신호가 바뀐 날: 알림 / 매주 화요일 아침(한국): 생존 확인용 주간 현황
- 알림 채널: 텔레그램, 이메일(Gmail) — 설정된 것만 사용
  환경변수: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO
  FORCE_NOTIFY=1 이면 변경 여부와 관계없이 발송 (첫 설치 테스트용)
"""
import json, os, smtplib, sys, urllib.parse, urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo
from tripod import (P, LABEL, alloc_text, gear, evaluate, load_live, load_csv,
                    fred_ndx)

KST = ZoneInfo("Asia/Seoul")


def cross_check(rows):
    """Yahoo 나스닥100 최근 값을 FRED와 대조. 0.5% 넘게 다르면 중단."""
    try:
        fred = fred_ndx()
    except Exception as e:
        print(f"[경고] FRED 대조 생략: {e}")
        return "FRED 접속 실패(대조 생략)"
    checked = 0
    for r in rows[-8:]:
        f = fred.get(r["date"])
        if f:
            diff = abs(r["ndx"] / f - 1)
            if diff > 0.005:
                raise SystemExit(f"[중단] {r['date']} Yahoo {r['ndx']:.2f} vs FRED {f:.2f} "
                                 f"({diff*100:.2f}% 차이) — 데이터 이상, 판정하지 않음")
            checked += 1
    if checked == 0:
        raise SystemExit("[중단] 최근 8거래일 중 FRED와 겹치는 날이 없음")
    return f"FRED 대조 {checked}일 일치"


def build_message(rows, check_note):
    valid = [r for r in rows if r["state"]]
    last, prev = valid[-1], valid[-2]
    changed = last["state"] != prev["state"]
    # 현재 상태가 시작된 날
    since = last["date"]
    for r in reversed(valid):
        if r["state"] != last["state"]:
            break
        since = r["date"]
    to_dd = (last["high52"] * (1 + P["dd_threshold"]) / last["ndx"] - 1) * 100
    head = "🔔 [트라이팟] 신호 변경 — 내일 장에서 리밸런싱" if changed else "📊 [트라이팟] 현황"
    lines = [head, f"기준: {last['date']} 미국 종가", ""]
    if changed:
        lines += [f"변경: {LABEL[prev['state']]} → {LABEL[last['state']]}",
                  f"이전: {alloc_text(prev['state'])} ({gear(prev['state']):.1f}배)",
                  f"목표: {alloc_text(last['state'])} ({gear(last['state']):.1f}배)",
                  "체결: 다음 미국 거래일 (T+1)", ""]
    else:
        lines += [f"상태: {LABEL[last['state']]} (since {since})",
                  f"보유: {alloc_text(last['state'])} ({gear(last['state']):.1f}배) — 변경 없음", ""]
    lines += [f"① 추세  NDX {last['ndx']:,.0f} / 250일선 {last['sma']:,.0f} ({last['gap']*100:+.2f}%)",
              f"   상승 문턱 +1% · 하락 문턱 −5%",
              f"② 공포  VIX10 {last['vix_ma']:.2f} (상승장 28 / 하락장 18)",
              f"③ 피로  52주 고점 대비 {last['dd']*100:.2f}% (문턱 −9%, 지수 {to_dd:+.1f}% 더 빠지면 도달)",
              "", f"검증: {check_note}",
              "※ 규칙 추적용 알림이며 투자 권유가 아닙니다."]
    return changed, head, "\n".join(lines)


def send_telegram(text):
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data, timeout=20)
    return True


def send_mail(subject, text):
    user, pw = os.getenv("GMAIL_USER"), os.getenv("GMAIL_APP_PASSWORD")
    if not (user and pw):
        return False
    msg = MIMEText(text, _charset="utf-8")
    msg["Subject"], msg["From"] = subject, user
    msg["To"] = os.getenv("MAIL_TO") or user
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:                       # 오프라인 테스트: python3 run_signal.py data/market.csv
        rows, note = load_csv(sys.argv[1]), "오프라인 CSV"
    else:
        rows = load_live()
        note = cross_check(rows)
    evaluate(rows)
    changed, subject, text = build_message(rows, note)
    print(text)

    weekly = datetime.now(KST).weekday() == 1   # 화요일(KST) = 미국 월요일 마감 후
    if changed or weekly or os.getenv("FORCE_NOTIFY") == "1":
        sent = [n for n, f in [("텔레그램", lambda: send_telegram(text)),
                               ("이메일", lambda: send_mail(subject, text))] if f()]
        print(f"\n발송: {', '.join(sent) if sent else '알림 채널 미설정'}")
    json.dump({"asof": rows[-1]["date"], "state": [r for r in rows if r["state"]][-1]["state"],
               "changed": changed}, open("last_signal.json", "w"), ensure_ascii=False)
