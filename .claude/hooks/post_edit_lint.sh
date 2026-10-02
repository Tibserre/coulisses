#!/bin/bash
# PostToolUse: format + lint the edited file with the tools of its project (nearest
# pyproject.toml or package.json). Silent on success; exit 2 feeds errors back to Claude.

file=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')
[ -f "$file" ] || exit 0

nearest() {  # nearest parent folder of $file holding $1
  d=$(dirname "$file")
  while [ "$d" != "/" ]; do
    [ -f "$d/$1" ] && { echo "$d"; return; }
    d=$(dirname "$d")
  done
}

case "$file" in
  */.venv/*|*/node_modules/*) exit 0 ;;
  *.py)
    project=$(nearest pyproject.toml)
    [ -n "$project" ] || exit 0
    uv run --project "$project" ruff format --quiet "$file" >/dev/null 2>&1
    out=$(uv run --project "$project" ruff check --fix --quiet "$file" 2>&1)
    if [ -n "$out" ]; then
      echo "ruff signale des problèmes restants dans $file :" >&2
      echo "$out" >&2
      exit 2
    fi
    ;;
  *.ts|*.tsx|*.css)
    project=$(nearest package.json)
    [ -n "$project" ] && [ -d "$project/node_modules" ] || exit 0
    (cd "$project" && npx --no-install prettier --write --log-level=silent "$file" >/dev/null 2>&1)
    ;;
esac
exit 0
