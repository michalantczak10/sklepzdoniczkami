#!/usr/bin/env bash
# Cleanup local CI artifacts and temporary files created while debugging backups
set -euo pipefail
echo "Cleaning local artifacts and temporary files..."
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# remove artifacts dir if present
if [ -d "artifacts" ]; then
  echo "Removing artifacts/ directory"
  rm -rf artifacts
fi
# remove temp gh_artifacts directories
for d in $(ls -d C:/temp/gh_artifacts* 2>/dev/null || true); do
  echo "Removing $d"
  rm -rf "$d" || true
done
# Remove any leftover backup files in repo root
rm -f db-backup-files-*.tgz || true
rm -f backup.dump* || true
rm -f *.enc* || true
# Suggest git clean for untracked files
echo "Done. To remove other untracked files interactively use: git clean -n -d && git clean -f -d"
exit 0
