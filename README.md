# pantry

A voice-driven app hub running on a Raspberry Pi 4.

Say the wake word, ask a question, get a spoken answer. Later: say a mode name
to scope the next requests to a specific app (coding, task tracking, ...), each
backed by its own toolset.

## Status

Milestone 1 â€” general mode. See `docs/roadmap.md`.

## Layout

    pantry/          the package
      modes/         one module per app mode; general is mode zero
      model_select.py  probes for a working LLM model at startup
    tools/           operator scripts (mic tests, model check)
    archive/         the original prototype, kept for reference
    recordings/      captured audio (gitignored)

## Setup

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    cp .env.example .env      # then add your key

Activate with the `venv` alias, or call `.venv/bin/python` directly.

## Hardware notes

- USB mic (C-Media PCM2902) and 3.5mm speaker; ALSA card numbers shift between
  boots, so resolve devices by name â€” see `tools/mictest.sh`.
- ALSA's `default` device is broken on this box (error 524). Address cards
  explicitly with `plughw:<card>,0`.

## Tools

    tools/mictest.sh 10     record and analyse signal quality
    tools/micloop.sh 6      record, then play back on the speaker
    tools/check_models.py   list which LLM models this key can actually use
