#!/usr/bin/env bash
# Post a ShipCheck report as one sticky PR comment, updated in place on every run.
#   scripts/pr_comment.sh <report.md> <pr-number> <owner/repo>      (needs GH_TOKEN with pull-requests: write)
set -euo pipefail
report="$1"; pr="$2"; repo="$3"
marker="<!-- shipcheck-report -->"
body="$marker
$(head -c 60000 "$report")"   # GitHub's comment limit is 65,536 characters

id="$(gh api "repos/$repo/issues/$pr/comments" --paginate \
      --jq ".[] | select(.body | startswith(\"$marker\")) | .id" | head -n1)"
if [ -n "$id" ]; then
  gh api -X PATCH "repos/$repo/issues/comments/$id" -f body="$body" > /dev/null
  echo "Updated ShipCheck comment $id on #$pr"
else
  gh api -X POST "repos/$repo/issues/$pr/comments" -f body="$body" > /dev/null
  echo "Posted ShipCheck comment on #$pr"
fi
