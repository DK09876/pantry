# pantry

A voice front end that dispatches to applications, running on a Raspberry Pi 4.

Say the wake word, ask for something, and it either answers or drives one of
the apps running alongside it. Today that is [LifeOS](https://github.com/DK09876/LifeOS),
a task tracker on the same Pi; the design goal is that adding a second app is
a new module and one registry entry, with no change to the voice loop.

**[Architecture and diagrams →](docs/architecture.md)**

## What it does

```
you: "hey pantry"                         chime
you: "what's on my plate today?"          reads back your tasks
you: "add buy milk tomorrow in Health"    writes to LifeOS, appears in the browser
you: "mark refill prescription as done"   updates it
you: "how tall is Mount Everest?"         answers directly
you: "what's the weather?"                says it cannot look that up
```

The last one matters: with no weather tool it declines rather than inventing
a number.

Voice is a capture inbox. Speech cannot supply an effort estimate or judge
urgency, so a spoken task lands in LifeOS as *Needs Details* for you to triage
rather than arriving on the planning board scored as though it had been
thought about. It carries whatever you did say — the due date, the domain, the
priority.

## Pipeline

| Stage | Runs | Component |
|---|---|---|
| Wake word | on device | openWakeWord (`hey pantry`, trained here — falls back to `hey jarvis`) |
| Endpointing | on device | Silero VAD |
| Speech to text | cloud | Google Web Speech |
| Reasoning | cloud | Gemini Flash Lite, with tool calling |
| Speech | on device | Piper (`en_US-ryan-medium`) |

Three of five stages are local. The intent is to move the other two.

## Tools

Every LifeOS tool is a thin call to LifeOS's assistant API (`/api/assistant`),
which runs the app's own actions on the Pi — so voice and the app can never
disagree about what "done" or "planned" means. The LifeOS side has the tests
for the behaviour.

| Say something like | Tool |
|---|---|
| "what's on today / Saturday" | `whats_on` |
| "what should I do next" | `whats_next` |
| "what's this week" / "what's overdue" / "brief me" | `this_week` / `whats_overdue` / `morning_brief` |
| "add call mom tomorrow" | `add_task` — only what you said; the rest waits in Needs Details |
| "put laundry on Saturday" / "I won't get to taxes today" | `plan_task` / `push_to_tomorrow` |
| "do the dishes again" | `do_again` |
| "I did laundry" / "I meditated" (yesterday too) | `mark_done` |
| "I read 12 pages" | `log_progress` |
| "how's my energy" / "make today a 5" | `energy_today` / `set_today_energy` |
| "tax docs is waiting on the accountant, chase Thursday" / "what am I waiting on" | `mark_waiting` / `whats_waiting` |
| "how did this week go" / "what's my meditation streak" | `week_review` / `habit_streak` |
| "add eggs to shopping" / "what's on the list" / "got the eggs" | `add_to_list` / `read_list` / `tick_off_list` |
| "remember the wifi code is 4471" / "what's the wifi code" | `add_note` / `find_note` |
| "undo that" | `undo_last` |

## Siri

`python -m pantry.server` listens on `127.0.0.1:8790`; LifeOS's `/api/voice`
forwards to it. An iOS Shortcut ("Dictate Text" → "Get Contents of URL" POST
`https://pai.tail57458f.ts.net/api/voice` with `{"text": …}` → "Speak Text"
of `reply`) makes it "Hey Siri, Pantry" on any Apple device on the tailnet.
Each device keeps a short conversation for follow-ups.

## Services

`deploy/pantry-api.service` (Siri endpoint) and `deploy/pantry-voice.service`
(the Pi's own mic, "hey pantry" — see [docs/wake-word.md](docs/wake-word.md)).

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

## Tests

```bash
.venv/bin/python -m pytest
```

68 tests, no audio hardware or network required: the LifeOS API is stubbed
and nothing constructs a `Speaker`. CI runs them on every pull request.

## Hardware notes

ALSA's `default` device is broken on this box (error 524), so cards are
addressed explicitly and resolved **by name** — indices move between boots and
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
