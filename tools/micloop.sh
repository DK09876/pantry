#!/usr/bin/env bash
# Record from the USB mic, then immediately play it back on the 3.5mm speaker.
#   ./micloop.sh [seconds]
set -euo pipefail

SECS="${1:-6}"
OUT="$HOME/development/recordings/loop_$(date +%Y%m%d_%H%M%S).wav"
PY="$HOME/development/ai_env/bin/python"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
mkdir -p "$(dirname "$OUT")"

# Resolve devices by name; card numbers shift between boots and USB ports.
MIC=$(arecord -l | awk -F'[ :]' '/USB PnP|USB Audio/ {print $2; exit}')
SPK=$(aplay   -l | awk -F'[ :]' '/bcm2835 Headphones/ {print $2; exit}')
[ -z "${MIC:-}" ] && { echo "ERROR: no USB mic (see 'arecord -l')" >&2; exit 1; }
[ -z "${SPK:-}" ] && { echo "ERROR: no headphone jack (see 'aplay -l')" >&2; exit 1; }
echo "mic=card$MIC  speaker=card$SPK"

echo
echo ">>> Recording ${SECS}s - SPEAK NOW <<<"
for i in 3 2 1; do printf "  %s...\r" "$i"; sleep 1; done
echo "  GO!        "
arecord -D "plughw:$MIC,0" -d "$SECS" -c 1 -r 48000 -f S16_LE "$OUT" 2>/dev/null

echo "Saved: $OUT"
"$PY" - "$OUT" <<'PY'
import sys, wave, math, numpy as np
w = wave.open(sys.argv[1]); sr = w.getframerate()
a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
dbfs = lambda v: 20 * math.log10(max(v, 1) / 32768)
win = int(sr * 0.05)
f = np.array([np.sqrt((a[i:i+win]**2).mean()) for i in range(0, len(a)-win, win)])
floor, loud, peak = np.percentile(f, 10), np.percentile(f, 90), float(np.abs(a).max())
print(f"  peak {dbfs(peak):6.1f} dBFS   floor {dbfs(floor):6.1f}   speech {dbfs(loud):6.1f}"
      f"   SNR {dbfs(loud)-dbfs(floor):5.1f} dB")
if peak >= 32700: print("  >> CLIPPING - lower gain")
elif dbfs(loud) - dbfs(floor) < 15: print("  >> weak speech/noise separation")
else: print("  >> good")
PY

echo
echo ">>> Playing back on speaker <<<"
# ALSA 'default' is broken on this box (err 524); address the card directly.
aplay -D "plughw:$SPK,0" "$OUT"
echo "Done. Replay: aplay -D plughw:$SPK,0 '$OUT'"
