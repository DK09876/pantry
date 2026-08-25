#!/usr/bin/env bash
# Record from the USB mic and report signal quality.
#   ./mictest.sh [seconds] [outfile]
set -euo pipefail

SECS="${1:-8}"
OUT="${2:-$HOME/development/recordings/mic_$(date +%Y%m%d_%H%M%S).wav}"
PY="$HOME/development/ai_env/bin/python"
mkdir -p "$(dirname "$OUT")"

# Resolve the USB mic's card number by name, not a hardcoded index.
CARD=$(arecord -l | awk -F'[ :]' '/USB PnP|USB Audio/ {print $2; exit}')
if [ -z "${CARD:-}" ]; then
  echo "ERROR: no USB mic found. Check 'arecord -l'." >&2
  exit 1
fi
echo "Using card $CARD (plughw:$CARD,0)"

echo
echo ">>> Recording ${SECS}s - SPEAK NOW <<<"
for i in 3 2 1; do printf "  %s...\r" "$i"; sleep 1; done
echo "  GO!        "

arecord -D "plughw:$CARD,0" -d "$SECS" -c 1 -r 48000 -f S16_LE "$OUT" 2>/dev/null
echo "Saved: $OUT"

"$PY" - "$OUT" <<'PY'
import sys, wave, math, numpy as np
w = wave.open(sys.argv[1]); sr = w.getframerate(); n = w.getnframes()
a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64)
dbfs = lambda v: 20 * math.log10(max(v, 1) / 32768)
rms, peak = float(np.sqrt((a**2).mean())), float(np.abs(a).max())

# Noise floor = quietest 10% of 50ms windows; speech = loudest 10%.
win = int(sr * 0.05)
frames = np.array([np.sqrt((a[i:i+win]**2).mean()) for i in range(0, len(a) - win, win)])
floor  = float(np.percentile(frames, 10))
speech = float(np.percentile(frames, 90))

print(f"\n  duration {n/sr:.1f}s @ {sr} Hz")
print(f"  RMS   {rms:8.0f}  ({dbfs(rms):6.1f} dBFS)")
print(f"  PEAK  {peak:8.0f}  ({dbfs(peak):6.1f} dBFS)")
print(f"  floor {floor:8.0f}  ({dbfs(floor):6.1f} dBFS)   loud {speech:8.0f}  ({dbfs(speech):6.1f} dBFS)")
print(f"  dynamic range: {dbfs(speech) - dbfs(floor):.1f} dB")

if peak >= 32700:   print("  >> CLIPPING - lower gain")
elif peak < 500:    print("  >> TOO QUIET - raise gain or move closer")
elif dbfs(floor) > -45: print("  >> NOISY room/mic - noise floor is high, STT will struggle")
elif dbfs(speech) - dbfs(floor) < 15: print("  >> weak separation between speech and noise")
else:               print("  >> good level")
PY

echo
echo "Play back on the Pi:  aplay '$OUT'"
