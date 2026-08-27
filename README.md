# pantry

A voice front end that dispatches to applications, running on a Raspberry Pi 4.

Say the wake word, ask for something, and it either answers or drives one of
the apps running alongside it. Today that is [LifeOS](https://github.com/DK09876/LifeOS),
a task tracker on the same Pi; the design goal is that adding a second app is
a new module and one registry entry, with no change to the voice loop.

**[Architecture and diagrams â†’](docs/architecture.md)**

## What it does

```
you: "hey jarvis"                         chime
you: "what's on my plate today?"          reads back your tasks
you: "add buy milk tomorrow in Health"    writes to LifeOS, appears in the browser
you: "mark refill prescription as done"   updates it
you: "how tall is Mount Everest?"         answers directly
you: "what's the weather?"                says it cannot look that up
```

The last one matters: with no weather tool it declines rather than inventing
a number.

## Pipeline

| Stage | Runs | Component |
|---|---|---|
| Wake word | on device | openWakeWord (`hey jarvis`) |
| Endpointing | on device | Silero VAD |
| Speech to text | cloud | Google Web Speech |
| Reasoning | cloud | Gemini Flash Lite, with tool calling |
| Speech | on device | Piper (`en_US-ryan-medium`) |

Three of five stages are local. The intent is to move the other two.

## Tools

Grouped by the app that owns them; a mode declares which sets are in scope.

| Tool | Does |
|---|---|
| `add_task` | name, optional due date, domain, priority |
| `list_tasks` | today / week / all, ranked by score |
| `complete_task` | loose name match |
| `add_domain` | new life area |
| `list_domains` | reads them back |

## Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
scripts/get_voice.sh                 # ~60MB Piper voice, gitignored
cp .env.example .env                 # then add GEMINI_API_KEY
.venv/bin/python assistant.py
```

## Tools for the operator

```bash
tools/mictest.sh 10      # record and analyse signal quality
tools/micloop.sh 6       # record, then play back
tools/listen.py --monitor  # live wake word scores, for tuning the threshold
tools/check_models.py    # which models this key can reach, and how fast
```

## Hardware notes

ALSA's `default` device is broken on this box (error 524), so cards are
addressed explicitly and resolved **by name** â€” indices move between boots and
USB ports. The microphone rejects 16 kHz, so capture runs at 48 kHz and is
decimated 3:1 with an anti-aliasing filter.

## Configuration

All optional; defaults are in `pantry/config.py`.

| Variable | Default |
|---|---|
| `PANTRY_WAKE_THRESHOLD` | `0.5` |
| `PANTRY_VAD_SILENCE_MS` | `700` |
| `PANTRY_PIPER_VOICE` | `models/piper/en_US-ryan-medium.onnx` |
| `PANTRY_LIFEOS_PROFILE` | `dk` |
| `GEMINI_MODEL` | probed at startup |
