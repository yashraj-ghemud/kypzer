"""Command-line helper to synthesize text to a WAV file using Coqui TTS.

This script is intended to be run with a Python interpreter that has the
`TTS` package installed (for example a dedicated Python 3.11 venv). It accepts
--text and --out arguments and writes a WAV file at the given path.

Usage (from repository root):
  .venv311\Scripts\python.exe -m src.assistant.coqui_runner --text "hello" --out C:\tmp\out.wav
"""
from __future__ import annotations
import argparse
import sys
import os

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--model', default=None, help='Optional TTS model name')
    args = parser.parse_args(argv)

    try:
        from TTS.api import TTS
    except Exception as e:
        print(f"ERROR: TTS import failed: {e}", file=sys.stderr)
        return 2

    model_name = args.model or os.environ.get('ASSISTANT_COQUI_MODEL')
    try:
        if model_name:
            tts = TTS(model_name=model_name, progress_bar=False, gpu=False)
        else:
            # Default: let TTS select a default compact model
            tts = TTS(progress_bar=False, gpu=False)
    except Exception as e:
        print(f"ERROR: failed loading model: {e}", file=sys.stderr)
        return 3

    try:
        tts.tts_to_file(text=args.text, file_path=args.out)
        return 0
    except Exception as e:
        print(f"ERROR: synthesis failed: {e}", file=sys.stderr)
        return 4
    

if __name__ == '__main__':
    raise SystemExit(main())
