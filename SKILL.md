---
name: "claude-usage-check"
description: "Claude 구독의 초과 사용 크레딧(extra usage credits)과 플랜 사용량 버킷(5시간 세션·주간)을 실측 조회하고 해석하는 절차. \"초과 크레딧 사용량\", \"크레딧 얼마 썼어\", \"클로드 사용량 확인\", \"오늘까지 크레딧\", \"주간 한도 얼마 남았어\", \"api로 사용량 확인\" 같은 요청에서 로드한다. 웹 UI가 아니라 API 가 정본이며, 절대 수치보다 직전 스냅숏 대비 변화량이 답이다."
---

# Claude 사용량·초과 크레딧 조회

조회 자체는 두 줄이면 끝난다. 이 스킬의 실제 내용은 **어느 경로로 부를지**와 **숫자를 어떻게 읽을지**다.

## 1. 조회 — 로컬 OAuth 토큰이 1순위

브라우저 로그인 상태와 무관하게 동작한다. Claude Code 가 설치돼 있으면 항상 이 경로를 먼저 쓴다.

```bash
CRED=/Users/<user>/.claude/.credentials.json   # $HOME 대신 절대경로 (아래 주의 참고)
TOK=$(python3 -c "import json;print(json.load(open('$CRED'))['claudeAiOauth']['accessToken'])")
curl -s https://api.anthropic.com/api/oauth/usage \
  -H "Authorization: Bearer $TOK" \
  -H "anthropic-beta: oauth-2025-04-20" \
  -H "Content-Type: application/json"
```

- **`$HOME`·`~` 를 쓰면 안 된다.** Aside 세션의 Bash 에서 `$HOME` 은 `/Users/<user>/.aside/runtime/home` 으로 리맵돼 `FileNotFoundError` 가 난다. 실제 홈 절대경로를 직접 적는다.

- **토큰은 절대 출력하지 않는다.** 셸 변수로만 옮기고, 값을 로그·응답·요약 어디에도 싣지 않는다.
- 토큰 수명은 약 1시간이고 Claude Code 가 자동 갱신한다. **매번 파일을 새로 읽는다** — 세션 변수에 캐시해 두면 다음 조회에서 401 이 난다. `claudeAiOauth.expiresAt`(epoch ms)로 남은 시간을 먼저 확인하면 만료 임박 여부를 미리 말해줄 수 있다.
- 계정·조직 확인이 필요하면 같은 토큰으로 `https://api.anthropic.com/api/oauth/profile`.
- `~/.claude/.credentials.json` 은 Bash 로 읽힌다. 반면 볼트 경로 등 일부 절대경로는 Bash 가 거부하므로, 거부당하면 `read_file` 툴을 시도한다.

**2순위 — 브라우저 쿠키 경로.** 위가 막혔을 때만 쓴다.

```js
const r = await fetch(`https://claude.ai/api/organizations/${orgUuid}/usage`);
```

- claude.ai 웹 세션이 살아 있어야 한다. 로그아웃 상태면 **403 `permission_error` / `account_session_invalid`** 이 돌아온다. 이때는 재로그인이 필요하고, Google SSO 비밀번호 단계에서 막히면 사용자에게 넘긴다 — 추측으로 비밀번호를 시도하지 않는다.
- REPL `fetch` 는 열린 탭에서 쿠키를 가져온다. `Tab ... belongs to a different browser profile` 오류가 나면 stale 한 탭 참조이므로, 같은 프로필에 탭을 하나 열고 다시 부른다.
- 응답 스키마는 OAuth 경로와 동일하다. 두 경로의 값은 서로 교차 검증 가능하다.

## 2. 응답 읽기

```jsonc
"extra_usage": { "used_credits": 4936.0, "monthly_limit": 100000, "utilization": 4.936,
                 "spend_limit_reached": false, "daily": null, "weekly": null }
"limits": [ { "kind": "session",       "percent": 67, "is_active": false, "resets_at": "..." },
            { "kind": "weekly_all",    "percent": 72, "is_active": true },
            { "kind": "weekly_scoped", "percent": 55, "scope": { "model": { "display_name": "Fable" } } } ]
```

- **`used_credits` 와 `monthly_limit` 은 센트 단위다.** 100 으로 나눠 달러로 환산한다 (4936 → $49.36, 100000 → $1,000.00).
- `used_credits` 는 **결제 주기 누적값**이다. 하루치 지출이 아니다. "오늘 얼마 썼어" 는 이 값에서 바로 나오지 않고 **두 스냅숏의 차이로 계산해야 하며, 그 사실을 답변에 명시한다.**
- `daily`·`weekly` 는 이 계정에서 항상 `null` 이다. 세분화된 기간별 값을 기대하지 말 것.
- `limits[].percent` 는 정수라 짧은 구간 비교에서는 반올림에 먹힌다. 몇 분짜리 관측으로 "안 움직였다" 고 단정하지 않는다.
- **`is_active: true` 인 버킷이 현재 발목을 잡는 한도다.** 5시간 세션과 주간은 서로 독립적으로 움직이므로 둘 다 보고한다.
- `weekly_scoped` 배열은 같은 날에도 비어서 돌아올 수 있다. 부재를 "해당 모델 사용량 0" 으로 읽지 않는다.
- `resets_at` 은 UTC다. **항상 KST 로 변환해서 제시한다** (UTC+9).
- `*_dollars` 필드들과 코드네임 버킷(`tangelo`, `nimbus_quill`, `cinder_cove` 등)은 대개 `null` 이다. 어느 하나가 non-null 로 바뀌면 새 한도 체계가 생겼다는 신호이므로 짚어준다.

## 3. 해석 — 크레딧이 도는 조건

**초과 크레딧은 플랜 버킷이 포화됐을 때만 소모된다.** 5시간 세션이 100%/critical 이 아니면 `used_credits` 는 몇 시간이고 그대로 멈춰 있는 게 정상이다. 값이 안 변했다고 조회가 실패한 게 아니다.

**크레딧을 쓰는 동안 주간 미터는 얼어붙는다.** Team 플랜 계정에서 실측 확인됐고 Anthropic 문서에는 없는 동작이다. 근거는 단순한 "평평함"이 아니라 **시점 정렬** — 포화 시작과 동시에 주간이 멈추고, 5시간 버킷이 리셋되자마자 크레딧이 멈추고 주간이 다시 오른다. 다만 **주간이 먼저 포화되는 경우**는 미측정이므로 그 상황까지 일반화하지 않는다.

실용적 함의: 이미 포화된 5시간 창에 무거운 배치를 몰아넣으면 **돈은 쓰지만 주간 예산은 아낀다.**

포화 후 소진율은 실측 $24~61/h 로 편차가 크다. **한 번 잰 속도로 외삽하지 말고 범위로 말한다.**

## 4. 보고 형식

한국어로, 표 + 델타 우선.

1. **직전 스냅숏 대비 변화량을 맨 앞에 놓는다.** 절대값만 주는 답은 이 사용자에게 불완전하다. 직전 기록은 에이전트의 메모리 저장소(세션 간에 남는 메모·노트)에서 찾는다.
2. 두 스냅숏이 **같은 결제 주기**(월초 리셋 기준)에 속하는지 확인한 뒤에만 차이를 계산한다.
3. 표: 초과 크레딧 / 월 한도 / 5시간 세션 / 주간 전체 / 주간 scoped, 각 행에 현재값과 직전값.
4. **측정 시각(KST)과 조회 경로를 명시한다.** 이 사용자는 결론의 출처를 되묻는다 — 실측인지 추정인지 항상 구분해서 적는다.
5. 선형 외삽(주간 소진 예상 시점 등)은 **추정이라고 이름표를 붙여서** 제시한다.
6. 조회 결과를 새 스냅숏으로 남긴다 — 타임스탬프가 붙은 이 기록만이 일별 지출의 유일한 출처다. 기록이 비면 며칠치 증가분을 어느 날에도 귀속시킬 수 없다.

## 5. 사용량이 튀었을 때

"왜 이렇게 많이 썼지" 로 이어지면 `~/.claude/projects/**/*.jsonl` 포렌식으로 넘어간다. 이 계정의 확인된 원인 구조는 **캐시 read 비용**(컨텍스트 크기 × 요청 수)이며, 모델 선택이 아니다. 실측 사례에서 비용의 55% 가 캐시 read 였고, 컨텍스트를 86% 까지 키운 장수 세션 2개가 전체의 34% 를 차지했다.

- 레버는 **컨텍스트 크기와 요청 수**다. 30~40% 에서 `/compact` 하면 턴당 read 비용이 약 10배 줄어든 사례가 있다.
- 플랜 한도가 차면 Claude Code 가 프롬프트 캐시 TTL 을 1h→5m 로 자동 강등한다. 턴 간격이 5분보다 길면 오히려 손해이므로 그 워크로드에선 `ENABLE_PROMPT_CACHING_1H=1` 로 고정한다.
- JSONL 집계 시 **한 줄을 여러 번 세지 않도록** 주의한다. 과거 이 버그로 모든 달러 수치가 약 2.2배 부풀려진 적이 있다.
