---
title: claude-usage-check
created: 2026-10-16
updated: 2026-10-16
tags: [domain/인공지능, area/ai에이전트]
source: ai
---

# claude-usage-check

> Claude 구독의 초과 사용 크레딧과 플랜 사용량 버킷(5시간 세션·주간)을 API 로 실측 조회하고, 숫자를 해석해 직전 스냅숏 대비 변화량으로 보고하는 절차 스킬이다.

## 하는 일

- 1순위는 Claude Code 의 로컬 OAuth 토큰으로 사용량 API 를 부르는 경로다. 토큰은 셸 변수로만 다루고 출력하지 않는다.
- 크레딧 단위(센트), 누적값 해석, 포화 조건, KST 변환, 사용량 급증 원인 분석까지 다룬다.

## 설치

에이전트 도구의 스킬 경로에 clone 하거나 링크한다.

```bash
git clone https://github.com/s12171934/claude-usage-check.git ~/.claude/skills/claude-usage-check
# 다른 도구는 그 도구의 스킬 경로에 링크한다. 예: ln -s ~/.claude/skills/claude-usage-check ~/.codex/skills/claude-usage-check
```

- Claude Code 가 설치되어 로그인된 macOS 기계를 전제로 한다.

## 구성과 공개 면

- [[20_Agents/skills/claude-usage-check/SKILL|SKILL.md]] — 스킬 본문. 형식은 에이전트 도구가 정한다.
- 공개 면은 스킬 이름(`claude-usage-check`)뿐이다. 다른 스킬은 이 이름으로만 이 스킬을 가리킨다.
