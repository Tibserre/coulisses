#!/bin/zsh
# Tidies the app's worktrees once their work is in main: each one holds its own .venv and
# web/node_modules (about 350 MB), so finished ones add up fast.
#
# A worktree under .claude/worktrees is removed only if all of these hold:
#   - its HEAD is in main (nothing committed would be lost);
#   - it has no change, tracked or untracked;
#   - every file git ignores there is rebuildable (.venv, node_modules, caches, build
#     outputs): an ignored .env, database, recording, key or local setting keeps it;
#   - no process runs from it or has it as its folder (a session, a dev service, a connector).
# `git worktree remove` is used without --force. Then the local branches merged into main
# and checked out nowhere are deleted with `git branch -d`.
#
# Usage: scripts/nettoyer-worktrees.sh            # says what it would do
#        scripts/nettoyer-worktrees.sh --retirer  # does it

set -euo pipefail

ROOT=$(git -C ${0:A:h} rev-parse --path-format=absolute --git-common-dir)
ROOT=${ROOT:h}
WORKTREES=$ROOT/.claude/worktrees
APPLY=""
[[ ${1:-} == --retirer ]] && APPLY=1

# Ignored paths that are only rebuilt from the repository or from caches: whole folders by
# name, and files by name or suffix.
REBUILDABLE_DIRS=(
  .venv node_modules __pycache__ .pytest_cache .ruff_cache .pyright .mypy_cache dist build
)
rebuildable() {
  local p=$1 d
  for d in $REBUILDABLE_DIRS; do
    [[ $p == $d/* || $p == */$d/* ]] && return 0
  done
  [[ ${p%/} == *.egg-info ]] && return 0
  [[ ${p:t} == .DS_Store || ${p:t} == *.tsbuildinfo ]] && return 0
  return 1
}

# Listed first, then searched in the shell: no pipe, so neither the search itself nor a
# closed pipe can change the answer. A listing that fails counts as « in use ».
in_use() {
  local dir=$1 procs cwds
  procs=$(ps -axww -o command=) || return 0
  [[ $procs == *"$dir/"* || $procs == *"$dir "* || $procs == *"$dir"$'\n'* ]] && return 0
  cwds=$(lsof -a -d cwd -Fn 2>/dev/null) || [[ -n $cwds ]] || return 0
  [[ $'\n'$cwds$'\n' == *$'\n'"n$dir"$'\n'* || $cwds == *$'\n'"n$dir/"* ]] && return 0
  return 1
}

removed=0 kept=0 failed=0 leaving=()
for dir in $WORKTREES/*(N/); do
  name=${dir:t}
  top=$(git -C $dir rev-parse --show-toplevel 2>/dev/null) || top=""
  if [[ ${top:A} != ${dir:A} ]]; then
    print "  laissé   $name : pas un worktree"
    continue
  fi
  head=$(git -C $dir rev-parse HEAD)
  branch=$(git -C $dir branch --show-current)
  why=""
  if ! git -C $ROOT merge-base --is-ancestor $head main; then
    why="pas dans main (${branch:-détaché})"
  elif ! state=$(git -C $dir status --porcelain); then
    why="état illisible"
  elif [[ -n $state ]]; then
    why="modifications en cours"
  else
    kept_files=()
    ignored=$(git -C $dir status --porcelain --ignored) || { why="état illisible"; }
    if [[ -z $why ]]; then
      for line in ${(f)ignored}; do
        [[ $line == '!! '* ]] || continue
        rebuildable ${line#!! } || kept_files+=(${line#!! })
      done
      (( ${#kept_files} )) && why="fichiers ignorés à garder : ${(j:, :)kept_files}"
    fi
    [[ -z $why ]] && in_use $dir && why="en usage"
  fi
  if [[ -n $why ]]; then
    print "  garde    $name : $why"
    kept=$((kept + 1))
    continue
  fi
  if [[ -z $APPLY ]]; then
    print "  retirerait $name (${branch:-détaché}, dans main)"
    removed=$((removed + 1))
    [[ -n $branch ]] && leaving+=($branch)
  elif git -C $ROOT worktree remove $dir; then
    print "  retiré   $name (${branch:-détaché})"
    removed=$((removed + 1))
  else
    print "  échec    $name : git refuse de le retirer"
    failed=$((failed + 1))
  fi
done

checked=(${(f)"$(git -C $ROOT worktree list --porcelain | awk '/^branch /{sub("refs/heads/", "", $2); print $2}')"})
merged=()
for b in ${(f)"$(git -C $ROOT branch --merged main --format='%(refname:short)')"}; do
  [[ $b == main ]] && continue
  (( ${checked[(Ie)$b]} )) && ! (( ${leaving[(Ie)$b]} )) && continue
  merged+=($b)
done

if [[ -n $APPLY ]]; then
  deleted=0
  for b in $merged; do
    if git -C $ROOT branch -q -d $b; then deleted=$((deleted + 1)); else failed=$((failed + 1)); fi
  done
  print "$removed worktree(s) retiré(s), $kept gardé(s), $deleted branche(s) fusionnée(s) supprimée(s), $failed échec(s)."
  (( failed == 0 ))
else
  print "$removed worktree(s) à retirer, $kept à garder, ${#merged} branche(s) fusionnée(s) à supprimer."
  (( removed + ${#merged} )) && print "Pour le faire : $0 --retirer"
  true
fi
