#!/usr/bin/env bash
# GitHub の Social preview（1280x640）を index.html から作る。
# アップロードは手で: リポジトリの Settings → General → Social preview
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
"$CHROME" --headless --hide-scrollbars --force-device-scale-factor=1 --window-size=1280,640 \
  --screenshot="$DIR/social.png" "file://$DIR/index.html"
