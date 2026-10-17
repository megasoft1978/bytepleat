#!/bin/sh
# Screenshot every preview state with headless Chrome. Not shipped.
# Usage: design/preview/shoot.sh [port] [state ...]   (serve the repo root first: python3 -m http.server <port>)
set -eu
PORT="${1:-8765}"; [ $# -gt 0 ] && shift
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/design/screenshots/app"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PROFILE="${TMPDIR:-/tmp}/bytepleat-preview-profile"
STATES="${*:-empty empty-extract empty-inspect dragover files format running running-unknown fold success success-extract error cancelled inspect inspect-small review empty-selection multiple history}"
mkdir -p "$OUT"
for state in $STATES; do
  for theme in light dark; do
    for size in 1280x800 960x640; do
      w="${size%x*}"; h="${size#*x}"
      rm -rf "$PROFILE"
      "$CHROME" --headless=new --disable-gpu --hide-scrollbars --user-data-dir="$PROFILE" \
        --window-size="$w,$h" --virtual-time-budget=4000 \
        --screenshot="$OUT/$state-$theme-$size.png" \
        "http://127.0.0.1:$PORT/design/preview/index.html?state=$state&theme=$theme" >/dev/null 2>&1 || echo "failed: $state $theme $size"
    done
  done
done
rm -rf "$PROFILE"
