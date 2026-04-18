#!/usr/bin/env bash
# Tag and push a release. Run this AFTER the PR is merged into main.
#
# Usage:  ./scripts/tag_release.sh v1.0.0 "Initial public release"
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <tag> [message]" >&2
  echo "example: $0 v1.0.0 \"Initial public release\"" >&2
  exit 2
fi

tag="$1"
message="${2:-Release $tag}"

# Be on main with a clean tree.
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "✗ Run this from main (currently on '$branch')." >&2
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "✗ Working tree has uncommitted changes. Commit or stash first." >&2
  exit 1
fi

git pull --ff-only origin main

# Verify tests + lint one more time before tagging.
echo "→ Running tests..."
python -m pytest tests/ -q
echo "→ Running ruff..."
python -m ruff check videokidnapper/ main.py scripts/ tests/

echo "→ Tagging $tag"
git tag -a "$tag" -m "$message"
git push origin "$tag"

echo "✓ Pushed $tag."
echo
echo "Next: open GitHub → Releases → Draft a new release"
echo "      Select tag '$tag', paste .github/RELEASE_NOTES_v1.0.0.md, Publish."
