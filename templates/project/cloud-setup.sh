#!/bin/bash
# Setup script of the Claude Code cloud environment (claude.ai, environment settings).
# It runs as root before each session starts, and its result is cached only when it ends in about
# five minutes with exit 0: it installs what the image lacks and nothing else (Python, Node, the
# JDK with Maven and Gradle, PostgreSQL, Docker, git and gh are already there). Add the project's
# own tools at the end, each step with `|| true`.
set -u

# The checkout the session works in: the script may start from it or from its parent.
repo=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

pids=()

# just: the recipes of the justfile (check, acceptance, serve). The CI template installs it the same way.
if ! command -v just >/dev/null 2>&1; then
  { python3 -m pip install --quiet rust-just || pip install --quiet rust-just; } >/dev/null 2>&1 &
  pids+=($!)
fi

# The browser of the acceptance suite, with its system libraries, in the version the project
# locks: the packages come from the project's own package.json (spec/acceptance, else the root).
for dir in "$repo/spec/acceptance" "$repo"; do
  if [ -f "$dir/package.json" ] && { [ "$dir" != "$repo" ] || grep -q playwright "$dir/package.json"; }; then
    (
      cd "$dir" &&
        { [ -d node_modules ] || npm ci --no-audit --no-fund --silent; } &&
        npx --no-install playwright install --with-deps chromium
    ) >/dev/null 2>&1 &
    pids+=($!)
    break
  fi
done

# The installs are independent: wait for all of them, whatever they say.
for pid in "${pids[@]+"${pids[@]}"}"; do
  wait "$pid" || true
done

# Project-specific installs go here, for instance:
#   apt-get install -y --no-install-recommends <package> || true

exit 0
