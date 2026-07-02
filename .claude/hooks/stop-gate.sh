#!/usr/bin/env bash
# Stop hook — ターン終了前の品質ゲート。未コミットの .py 変更があるときだけ
# ruff / black --check / basedpyright / pytest を回し、失敗なら
# {"decision":"block","reason":"..."} を返して Claude に自己修正させる（自走ループの中核）。
#
# 安全弁:
# - stop_hook_active が真なら素通し（block → 修正 → 再Stop の無限ループ防止。
#   2周目は素通しになるため、直せない失敗で永久に止まることはない）。
# - pyproject.toml / uv / 各ツールが無い段階（Phase 1 以前）は素通し。
# - 純粋な会話ターン（.py の未コミット変更なし）は素通し（毎ターンの待ち時間を作らない）。

input=$(cat)

active=$(printf '%s' "$input" | python3 -c 'import sys,json
try:
    print(1 if json.load(sys.stdin).get("stop_hook_active") else 0)
except Exception:
    print(0)' 2>/dev/null)
[ "$active" = "1" ] && exit 0

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
[ -f pyproject.toml ] || exit 0
command -v uv >/dev/null 2>&1 || exit 0

# 未コミットの .py 変更（未追跡含む）が無ければ何もしない
git status --porcelain 2>/dev/null | grep -q '\.py$' || exit 0

fail=""
run_gate() {
  # $1=表示名 $2...=コマンド。ツール未導入なら SKIP（uv run が解決できない場合）
  local name="$1"; shift
  local out
  if ! out=$(uv run "$@" 2>&1); then
    # ツール自体が無い（No such command 等）なら SKIP 扱い
    if printf '%s' "$out" | grep -qiE 'No such (command|file)|not found|Failed to spawn'; then
      return 0
    fi
    fail="${name} 失敗:
${out}"
    return 1
  fi
  return 0
}

run_gate "ruff check"    ruff check . &&
run_gate "black --check" black --check -q . &&
run_gate "basedpyright"  basedpyright &&
{ ls tests/test_*.py >/dev/null 2>&1 && run_gate "pytest" pytest -q -x || true; }

[ -z "$fail" ] && exit 0

FAIL_TEXT="$fail" python3 - <<'PY'
import json, os
reason = os.environ["FAIL_TEXT"][:2000]
print(json.dumps({
    "decision": "block",
    "reason": "品質ゲート未通過（/qa 相当）。以下を修正してから終了してください。\n" + reason,
}, ensure_ascii=False))
PY
exit 0
