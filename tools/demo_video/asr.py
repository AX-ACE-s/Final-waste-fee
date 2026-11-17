"""TTS 결과 검증용 한국어 음성인식 (sherpa-onnx zipformer-korean)."""
import sys
import numpy as np, soundfile as sf, sherpa_onnx
import os
A = os.environ.get("ASR_MODEL_DIR", os.path.join(os.path.dirname(__file__), "models", "sherpa-onnx-zipformer-korean-2024-06-24"))
_r = None
def rec():
    global _r
    if _r is None:
        _r = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=f"{A}/encoder-epoch-99-avg-1.int8.onnx", decoder=f"{A}/decoder-epoch-99-avg-1.onnx",
            joiner=f"{A}/joiner-epoch-99-avg-1.int8.onnx", tokens=f"{A}/tokens.txt", num_threads=4)
    return _r
def transcribe(path):
    x, sr = sf.read(path, dtype="float32")
    if x.ndim > 1: x = x.mean(1)
    if sr != 16000:
        n = int(len(x) * 16000 / sr); x = np.interp(np.linspace(0, len(x)-1, n), np.arange(len(x)), x).astype("float32"); sr = 16000
    s = rec().create_stream(); s.accept_waveform(sr, x); rec().decode_stream(s)
    return s.result.text
if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, "→", transcribe(p))
