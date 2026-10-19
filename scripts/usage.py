#!/usr/bin/env python3
"""Claude 사용량 API 를 한 번 조회해 해석된 스냅숏을 찍고, 직전 스냅숏 대비 변화량을 함께 낸다.

토큰은 macOS 키체인(Claude Code 가 실제로 갱신하는 곳)을 먼저 읽고, 없거나 만료면
~/.claude/.credentials.json 으로 내려간다. 토큰 값은 어디에도 출력하지 않는다.

사용법: usage.py [--no-save] [--raw]
  --no-save  스냅숏을 기록하지 않는다 (확인만 할 때)
  --raw      해석 전 API 응답 원문을 함께 출력한다
스냅숏 위치: $CLAUDE_USAGE_SNAPSHOTS, 없으면 <실제 홈>/.local/state/claude-usage-check/snapshots.jsonl
"""
import json
import os
import pwd
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
API = "https://api.anthropic.com/api/oauth/usage"
# Aside 세션 등은 $HOME 을 리맵하므로 계정의 실제 홈을 쓴다.
REAL_HOME = pwd.getpwuid(os.getuid()).pw_dir


def load_token():
    """(token, source, expires_in_min) — 유효한 첫 후보. 없으면 종료."""
    candidates = []
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            candidates.append(("keychain", json.loads(out.stdout)))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    cred = os.path.join(REAL_HOME, ".claude", ".credentials.json")
    try:
        with open(cred) as f:
            candidates.append(("credentials.json", json.load(f)))
    except (OSError, ValueError):
        pass

    expired = []
    for source, data in candidates:
        oauth = data.get("claudeAiOauth") or {}
        tok, exp = oauth.get("accessToken"), oauth.get("expiresAt")
        if not tok:
            continue
        mins = None if exp is None else round((exp / 1000 - time.time()) / 60)
        if mins is not None and mins <= 0:
            expired.append(f"{source}({-mins}분 전 만료)")
            continue
        return tok, source, mins
    sys.exit("유효한 토큰 없음: " + (", ".join(expired) or "키체인·credentials.json 모두 없음")
             + " — Claude Code 를 한 번 실행해 토큰을 갱신한 뒤 다시 조회한다.")


def fetch(tok):
    req = urllib.request.Request(API, headers={
        "Authorization": f"Bearer {tok}",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"API {e.code}: {e.read().decode(errors='replace')[:300]}")


def to_kst(iso):
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def interpret(raw):
    ex = raw.get("extra_usage") or {}
    used, limit = ex.get("used_credits"), ex.get("monthly_limit")
    limits = []
    for b in raw.get("limits") or []:
        name = b.get("kind")
        model = ((b.get("scope") or {}).get("model") or {}).get("display_name")
        if model:
            name = f"{name}:{model}"
        limits.append({"bucket": name, "percent": b.get("percent"), "severity": b.get("severity"),
                       "active": b.get("is_active"), "resets_kst": to_kst(b.get("resets_at"))})
    # 평소 채워져 오는 키 밖에서 non-null 이 생기거나 *_dollars 가 채워지면 새 한도 체계의 신호다.
    known = {"extra_usage", "limits", "five_hour", "seven_day", "spend",
             "member_dashboard_available", "weekly_scoped_shares"}
    unknown = sorted(k for k, v in raw.items() if k not in known and v not in (None, [], {}))
    unknown += sorted(f"{k}.{f}" for k in ("five_hour", "seven_day")
                      for f, v in (raw.get(k) or {}).items() if f.endswith("_dollars") and v is not None)
    return {
        "at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "at_epoch": int(time.time()),
        "extra_used_usd": None if used is None else round(used / 100, 2),
        "extra_limit_usd": None if limit is None else round(limit / 100, 2),
        "spend_limit_reached": ex.get("spend_limit_reached"),
        "limits": limits,
        "unknown_nonnull_keys": unknown,
    }


def snapshot_path():
    return os.environ.get("CLAUDE_USAGE_SNAPSHOTS") or os.path.join(
        REAL_HOME, ".local", "state", "claude-usage-check", "snapshots.jsonl")


def last_snapshot(path):
    try:
        with open(path) as f:
            lines = [l for l in f if l.strip()]
        return json.loads(lines[-1]) if lines else None
    except (OSError, ValueError):
        return None


def delta(prev, cur):
    if not prev:
        return {"note": "직전 스냅숏 없음 — 이번 값이 첫 기준점이다"}
    p_month = datetime.fromtimestamp(prev["at_epoch"], KST).strftime("%Y-%m")
    c_month = datetime.fromtimestamp(cur["at_epoch"], KST).strftime("%Y-%m")
    d = {"since_kst": prev["at_kst"],
         "hours": round((cur["at_epoch"] - prev["at_epoch"]) / 3600, 1)}
    if p_month != c_month:
        d["note"] = "결제 주기(월)가 달라 크레딧 차이를 계산하지 않는다"
    elif cur["extra_used_usd"] is not None and prev.get("extra_used_usd") is not None:
        d["extra_used_usd"] = round(cur["extra_used_usd"] - prev["extra_used_usd"], 2)
    pl = {b["bucket"]: b["percent"] for b in prev.get("limits", [])}
    d["limits_pp"] = {b["bucket"]: b["percent"] - pl[b["bucket"]]
                      for b in cur["limits"]
                      if b["percent"] is not None and pl.get(b["bucket"]) is not None}
    return d


def main():
    args = set(sys.argv[1:])
    tok, source, mins = load_token()
    raw = fetch(tok)
    del tok
    cur = interpret(raw)
    path = snapshot_path()
    out = {"source": source, "token_expires_in_min": mins, "snapshot": cur,
           "delta": delta(last_snapshot(path), cur)}
    if "--raw" in args:
        out["raw"] = raw
    if "--no-save" not in args:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(cur, ensure_ascii=False) + "\n")
        out["saved_to"] = path
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
