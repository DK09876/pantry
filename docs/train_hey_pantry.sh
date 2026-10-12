#!/usr/bin/env bash
# Train an openWakeWord model for "hey pantry".
#
# Runs inside the OrbStack Ubuntu 22.04 machine "wakeword" (the training
# recipe pins Linux-only, Python 3.10-era packages). The workspace is the
# Mac folder ~/Desktop/Development/wakeword, mounted at the same path.
#
# Steps follow openWakeWord's notebooks/automatic_model_training.ipynb:
# data downloads, synthetic clip generation, augmentation, training, ONNX
# export. Re-running skips anything already present.
set -euo pipefail

WS="/Users/dikshant/Desktop/Development/wakeword"
VENV="$HOME/oww-venv"
cd "$WS"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# --- system packages ------------------------------------------------------
if ! command -v ffmpeg >/dev/null || ! python3.10 -m venv --help >/dev/null 2>&1; then
  log "installing system packages"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.10-venv python3-dev build-essential ffmpeg libsndfile1 espeak-ng wget git >/dev/null
fi

# --- python environment ---------------------------------------------------
if [ ! -d "$VENV" ]; then
  log "creating venv"
  python3.10 -m venv "$VENV"
fi
source "$VENV/bin/activate"
if [ ! -f "$VENV/.deps-done" ]; then
  log "installing python deps (CPU torch)"
  pip install -q --upgrade pip wheel
  pip install -q torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu
  pip install -q piper-phonemize==1.1.0 webrtcvad
  pip install -q mutagen==1.47.0 torchinfo==1.8.0 torchmetrics==1.2.0 speechbrain==0.5.14 \
    audiomentations==0.33.0 torch-audiomentations==0.11.0 acoustics==0.2.6 pronouncing==0.2.0 \
    datasets==2.14.6 deep-phonemizer==0.0.19 'numpy<2' scipy pyyaml tqdm onnx onnxruntime soundfile
  pip install -q -e "$WS/openWakeWord"
  touch "$VENV/.deps-done"
fi

# datasets 2.14 predates pyarrow 15's removal of PyExtensionType.
python -c "import pyarrow, sys; sys.exit(0 if int(pyarrow.__version__.split('.')[0]) < 15 else 1)" 2>/dev/null \
  || pip install -q 'pyarrow<15'

# pronouncing still imports pkg_resources, which new setuptools dropped.
python -c "import pkg_resources" 2>/dev/null || pip install -q 'setuptools<70'
python -c "import espeak_phonemizer" 2>/dev/null || pip install -q espeak-phonemizer

# --- piper sample generator -------------------------------------------------
# openWakeWord's trainer imports generate_samples from the repo root, which is
# the dscripka fork's layout (rhasspy's current repo moved it into a package).
PSG="$WS/piper-sample-generator"
[ -d "$PSG" ] || git clone -q https://github.com/dscripka/piper-sample-generator "$PSG"
if [ ! -s "$PSG/models/en-us-libritts-high.pt" ]; then
  log "downloading TTS generator model"
  wget -q -O "$PSG/models/en-us-libritts-high.pt" \
    'https://github.com/rhasspy/piper-sample-generator/releases/download/v1.0.0/en-us-libritts-high.pt'
fi

# --- openWakeWord feature models ------------------------------------------------
MODELS="$WS/openWakeWord/openwakeword/resources/models"
mkdir -p "$MODELS"
for f in embedding_model.onnx embedding_model.tflite melspectrogram.onnx melspectrogram.tflite; do
  [ -f "$MODELS/$f" ] || wget -q -O "$MODELS/$f" "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/$f"
done

# --- datasets ------------------------------------------------------------------
mkdir -p data && cd data
[ -f validation_set_features.npy ] || { log "downloading validation features"; wget -q https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy; }
[ -f openwakeword_features_ACAV100M_2000_hrs_16bit.npy ] || { log "downloading ACAV100M negative features (~17GB)"; wget -q https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy; }
cd "$WS"

python - <<'PY'
import os, numpy as np, scipy.io.wavfile, datasets
from pathlib import Path
from tqdm import tqdm
os.chdir("data")
if not os.path.exists("mit_rirs") or len(os.listdir("mit_rirs")) < 200:
    os.makedirs("mit_rirs", exist_ok=True)
    print("downloading room impulse responses", flush=True)
    for row in tqdm(datasets.load_dataset("davidscripka/MIT_environmental_impulse_responses", split="train", streaming=True)):
        name = row['audio']['path'].split('/')[-1]
        scipy.io.wavfile.write(os.path.join("mit_rirs", name), 16000, (row['audio']['array']*32767).astype(np.int16))
if not os.path.exists("fma") or len(os.listdir("fma")) < 200:
    os.makedirs("fma", exist_ok=True)
    print("downloading background music (FMA, 2h)", flush=True)
    fma = iter(datasets.load_dataset("rudraml/fma", name="small", split="train", streaming=True).cast_column("audio", datasets.Audio(sampling_rate=16000)))
    for i in tqdm(range(2*3600//30)):
        row = next(fma)
        name = row['audio']['path'].split('/')[-1].replace(".mp3", ".wav")
        scipy.io.wavfile.write(os.path.join("fma", name), 16000, (row['audio']['array']*32767).astype(np.int16))
PY

# AudioSet noise is a nice-to-have; its hosting moves around. Use it if the
# download works, otherwise train on music + the precomputed negatives.
if [ ! -d data/audioset_16k ] || [ "$(ls data/audioset_16k | wc -l)" -lt 500 ]; then
  log "trying AudioSet background noise (optional)"
  mkdir -p data/audioset data/audioset_16k
  if wget -q -O data/audioset/bal_train09.tar https://huggingface.co/datasets/agkphysics/AudioSet/resolve/main/data/bal_train09.tar \
     && [ -s data/audioset/bal_train09.tar ]; then
    (cd data/audioset && tar -xf bal_train09.tar)
    find data/audioset/audio -name '*.flac' | while read -r f; do
      ffmpeg -loglevel error -y -i "$f" -ar 16000 -ac 1 "data/audioset_16k/$(basename "${f%.flac}").wav"
    done
  else
    log "AudioSet unavailable - continuing without it"
    rm -f data/audioset/bal_train09.tar
  fi
fi
BACKGROUND='["./data/fma"]'
if [ "$(ls data/audioset_16k 2>/dev/null | wc -l)" -ge 500 ]; then BACKGROUND='["./data/audioset_16k", "./data/fma"]'; fi
export BACKGROUND

# --- training config -------------------------------------------------------
python - <<'PY'
import yaml
cfg = yaml.safe_load(open("openWakeWord/examples/custom_model.yml"))
cfg.update({
    "target_phrase": ["hey pantry"],
    "model_name": "hey_pantry",
    # Words that sound close, so the model learns to tell them apart.
    "custom_negative_phrases": ["hey party", "hey patty", "hey panther", "hey andre", "hey plenty",
                                "pantry", "hey pancake", "hey penny", "hey candy", "hey country"],
    "n_samples": 6000,
    "n_samples_val": 1500,
    "steps": 25000,
    "target_accuracy": 0.7,
    "target_recall": 0.5,
    "output_dir": "./out",
    "piper_sample_generator_path": "./piper-sample-generator",
    "rir_paths": ["./data/mit_rirs"],
    "background_paths": __import__("json").loads(__import__("os").environ["BACKGROUND"]),
    "false_positive_validation_data_path": "./data/validation_set_features.npy",
    "feature_data_files": {"ACAV100M_sample": "./data/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"},
})
yaml.safe_dump(cfg, open("hey_pantry.yml", "w"))
print("config written")
PY

log "step 1/3: generating synthetic clips"
python openWakeWord/openwakeword/train.py --training_config hey_pantry.yml --generate_clips
log "step 2/3: augmenting clips"
python openWakeWord/openwakeword/train.py --training_config hey_pantry.yml --augment_clips
log "step 3/3: training"
python openWakeWord/openwakeword/train.py --training_config hey_pantry.yml --train_model
log "DONE: $(ls -la out/hey_pantry.onnx 2>/dev/null)"
