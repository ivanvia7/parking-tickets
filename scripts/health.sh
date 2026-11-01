#!/usr/bin/env bash
# Run check-city for every city. A broken city's output goes to <dir>/<slug>.txt,
# which the health workflow turns into one issue per city.
# Usage: scripts/health.sh [dir]   (default: health)
set -u
out="${1:-health}"
mkdir -p "$out"
failed=()
for slug in $(uv run parking-tickets cities); do
  if result=$(uv run parking-tickets check-city "$slug" 2>&1); then
    echo "$result"
  else
    echo "$result" | tee "$out/$slug.txt"
    failed+=("$slug")
  fi
done
if [ ${#failed[@]} -gt 0 ]; then
  echo "broken cities: ${failed[*]}" >&2
  exit 1
fi
