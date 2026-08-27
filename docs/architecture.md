# Architecture

pantry is a voice front end that dispatches to applications. It runs on a
Raspberry Pi 4 alongside the apps it drives.

The design goal is that adding a second application is a new module and one
registry entry, and the voice loop never changes.

## System

```mermaid
flowchart LR
    subgraph pi["Raspberry Pi 4"]
        direction TB
        pantry["pantry<br/>voice assistant"]
        lifeos["LifeOS<br/>Next.js"]
        db[("SQLite")]
        pantry -->|HTTP localhost| lifeos
        lifeos --> db
    end

    mic["USB mic"] --> pantry
    pantry --> spk["USB speaker"]

    subgraph cloud["Cloud"]
        stt["Google<br/>Speech to Text"]
        llm["Gemini<br/>Flash Lite"]
    end

    pantry -.-> stt
    pantry -.-> llm

    laptop["Laptop / phone<br/>browser"] -->|HTTPS via Tailscale| lifeos

    classDef local fill:#1D9E75,stroke:#0F6E56,color:#fff
    classDef remote fill:#D85A30,stroke:#993C1D,color:#fff
    class pantry,lifeos,db local
    class stt,llm remote
```

Solid lines stay on the device or the local network. Dashed lines leave it.
Two of the five pipeline stages are still remote; the rest run on the Pi.

## Voice pipeline

```mermaid
flowchart TD
    A["Microphone<br/>48 kHz, decimated 3:1"] --> B["Wake word<br/>openWakeWord"]
    B -->|"'hey jarvis'"| C["Endpointing<br/>Silero VAD"]
    C -->|utterance| D["Speech to text<br/>Google Web Speech"]
    D -->|text| E["Reasoning<br/>Gemini + tools"]
    E -->|reply| F["Speech<br/>Piper, on device"]
    F --> G["Speaker"]
    E -.->|tool call| H["LifeOS API"]
    H -.->|result| E

    classDef local fill:#1D9E75,stroke:#0F6E56,color:#fff
    classDef remote fill:#D85A30,stroke:#993C1D,color:#fff
    class A,B,C,F,G,H local
    class D,E remote
```

Measured on the Pi:

| Stage | Time |
|---|---|
| Wake word | ~0.1 s, 0.000 idle vs 0.96+ on detection |
| Endpointing | 700 ms of silence ends an utterance |
| Speech to text | 0.3â€“0.6 s |
| Gemini | 0.5â€“2 s healthy, 10â€“25 s when degraded |
| Piper | 0.32 Ã— realtime |

The microphone rejects 16 kHz, so audio is captured at 48 kHz and decimated
with an anti-aliasing filter. Without one, everything above 8 kHz folds back
into the speech band, and the microphone's noise is broadband.

## Modes and tools

A mode is scoped context: a system prompt plus which application toolsets are
in scope. Identity â€” whose data a tool touches â€” is a separate axis, so
`add_task` is written once and works for any profile.

```mermaid
flowchart TD
    U["Utterance"] --> M{"Active mode"}
    M --> G["general<br/>tools: lifeos"]
    M -.-> C["coding<br/>not built"]
    M -.-> T["tasks<br/>not built"]

    G --> R["Tool registry"]
    C -.-> R
    T -.-> R

    R --> L["lifeos<br/>add_task, list_tasks,<br/>complete_task,<br/>add_domain, list_domains"]
    R -.-> X["another app<br/>a module and<br/>one registry entry"]

    classDef built fill:#1D9E75,stroke:#0F6E56,color:#fff
    classDef planned fill:#B4B2A9,stroke:#5F5E5A,color:#fff,stroke-dasharray: 4 4
    class G,R,L built
    class C,T,X planned
```

Tools are plain Python functions. Their type hints become the parameter
schema and their docstrings tell the model when to call them, so the wording
of a docstring is functional code.

## Adding a task by voice

```mermaid
sequenceDiagram
    participant U as User
    participant P as pantry
    participant Gm as Gemini
    participant L as LifeOS
    participant B as Browser

    U->>P: "hey jarvis"
    P->>U: chime
    U->>P: "add buy milk tomorrow in Health"
    P->>P: VAD ends utterance
    P->>Gm: transcript + tool schemas
    Gm->>P: call add_task(...)
    P->>L: POST /api/data?profile=â€¦
    L->>L: write to SQLite
    L->>P: ok
    P->>Gm: tool result
    Gm->>P: "Added buy milk to Health"
    P->>U: Piper speaks it
    B->>L: poll (every 2 s)
    L->>B: changed payload
    B->>B: task appears
```

The browser learns about the change by polling rather than being pushed to.
A dropped stream needs reconnect and backoff logic; an unchanged poll is one
request whose body matches the last one, so it costs a round trip and
nothing else.

## Choices worth explaining

**Wake word on device.** The prototype detected the wake word by sending
four second chunks of room audio to Google continuously. openWakeWord runs
locally, so the microphone stays on the Pi until the wake word fires.

**Piper over a cloud voice.** Removes a network call from every reply, and
the demo does not depend on a speech service being healthy. The `high`
quality models sound better but synthesise at roughly 2Ã— slower than
realtime on a Pi 4, which stalls every reply â€” so `medium` with the
expressiveness parameters raised is the usable tier.

**Whole replies, not streamed.** Streaming emits `function_call` parts with
no text, which stalls a text-only consumer; Google's SDK advisory puts
automatic function calling on `send_message`. Streaming saved a fraction of
a second and cost the reliability of the whole tool path.

**Registry keyed by application.** A flat list of tools would work today
with one app. Keyed by app, a mode can scope which sets are live, which is
what keeps the model from choosing among every function ever registered.

## Not built yet

Local speech to text (whisper.cpp is workable on this hardware but ~3 s),
a local language model, a second application toolset, speaker identification
for per-person profiles, and barge-in.
