#!/usr/bin/env bash
# Download a Piper voice.
#
# Voices are ~60MB each and are build artifacts, not source, so they are
# gitignored and fetched on demand.
#
#   scripts/get_voice.sh                      the default voice
#   scripts/get_voice.sh en_US-amy-medium     a specific one
set -euo pipefail

VOICE="${1:-en_US-ryan-medium}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/models/piper"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en"

# en_US-ryan-medium -> en_US/ryan/medium
IFS='-' read -r lang name quality <<< "$VOICE"
REMOTE="$BASE/$lang/$name/$quality/$VOICE"

mkdir -p "$DEST"
for ext in onnx onnx.json; do
  if [ -f "$DEST/$VOICE.$ext" ]; then
    echo "have $VOICE.$ext"
  else
    echo "fetching $VOICE.$ext"
    curl -fsSL -o "$DEST/$VOICE.$ext" "$REMOTE.$ext"
  fi
done
echo "ready: $DEST/$VOICE.onnx ($(du -h "$DEST/$VOICE.onnx" | cut -f1))"
