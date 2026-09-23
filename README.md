# 트라이팟 신호 알림 + 백테스트

유튜브 '송팀장' 채널이 공개한 트라이팟 규칙을 매 거래일 판정해 **텔레그램/이메일**로 알려 줍니다.
파이썬 표준 라이브러리만 사용합니다. 규칙 추적용이며 투자 권유가 아닙니다.

## 알림 규칙
- **신호가 바뀐 날**: 즉시 알림 (다음 미국 거래일에 리밸런싱)
- **매주 화요일 아침**: 변경이 없어도 현황 알림 (시스템이 살아 있다는 확인)
- 실행 시각: 한국시간 화~토 07:30 (미국 장 마감 후)
- 안전장치: Yahoo 나스닥100 값을 FRED와 대조, 0.5% 넘게 다르면 판정하지 않고 실패 → GitHub이 실패 메일 발송

## 설치 (약 15분, 1회)
1. github.com 가입 → **New repository** (Public 권장) → 이 폴더 파일 전부 업로드
   - `.github/workflows/tripod.yml` 은 숨김 폴더라 드래그가 안 되면
     **Add file → Create new file** 에 경로째 입력 후 내용 붙여넣기
2. 알림 채널 설정: **Settings → Secrets and variables → Actions → New repository secret**

   **텔레그램 (권장, 휴대폰 푸시)**
   - 텔레그램에서 `@BotFather` → `/newbot` → 발급된 토큰 → `TELEGRAM_TOKEN`
   - 만든 봇에게 아무 메시지나 보낸 뒤 브라우저로
     `https://api.telegram.org/bot<토큰>/getUpdates` 열기 → `"chat":{"id":숫자` → `TELEGRAM_CHAT_ID`

   **이메일 (Gmail)**
   - Google 계정 2단계 인증 켜기 → myaccount.google.com/apppasswords 에서 앱 비밀번호 생성
   - `GMAIL_USER`(주소), `GMAIL_APP_PASSWORD`(16자리), 받는 주소가 다르면 `MAIL_TO`
3. **Actions 탭 → 트라이팟 일일 신호 → Run workflow** → 몇 분 뒤 첫 알림 도착하면 완료

> GitHub은 60일간 저장소 활동이 없으면 예약 실행을 끌 수 있습니다. 꺼지기 전 메일이 오며,
> Actions 탭에서 다시 켜면 됩니다. 두 달에 한 번 **Run workflow**를 눌러 두면 확실합니다.

## 백테스트 재현
```
python3 backtest.py                      # 1991-01 ~ 2026-09-04 (35년)
python3 backtest.py --start 20100211     # TQQQ 상장 이후만
```
- `data/market.csv`: 나스닥100·VIX·13주 T-bill 일간 종가 (출처: Yahoo Finance, FRED, CBOE;
  github.com/MinorPassCpa/tripod 공개 데이터)
- 가상 ETF = 지수 × 레버리지 − 조달비용(T-bill+0.5%) − 운용보수 + 배당 0.45%/년, 매매비용 3bp
- 체결: T일 종가 신호 → T+1 종가 체결
- 세금(국내 거주자 해외주식 양도세 22%)과 환율은 반영하지 않음

## 파일
| 파일 | 역할 |
|---|---|
| `tripod.py` | 규칙 파라미터·지표·판정, 시세 수집 |
| `run_signal.py` | 일일 판정 + 알림 (`python3 run_signal.py data/market.csv` 로 오프라인 테스트) |
| `backtest.py` | 35년 백테스트 |
| `.github/workflows/tripod.yml` | 자동 실행 스케줄 |
