"""Supertonic 3 (sherpa-onnx, 오프라인) 한국어 TTS."""
import sys, time, json
import sherpa_onnx, soundfile as sf

import os
M = os.environ.get("TTS_MODEL_DIR", os.path.join(os.path.dirname(__file__), "models", "sherpa-onnx-supertonic-3-tts-int8-2026-05-11"))
_tts = None

def tts():
    global _tts
    if _tts is None:
        cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            supertonic=sherpa_onnx.OfflineTtsSupertonicModelConfig(
                duration_predictor=f"{M}/duration_predictor.int8.onnx", text_encoder=f"{M}/text_encoder.int8.onnx",
                vector_estimator=f"{M}/vector_estimator.int8.onnx", vocoder=f"{M}/vocoder.int8.onnx",
                tts_json=f"{M}/tts.json", unicode_indexer=f"{M}/unicode_indexer.bin", voice_style=f"{M}/voice.bin"),
            num_threads=4, provider="cpu"))
        assert cfg.validate()
        _tts = sherpa_onnx.OfflineTts(cfg)
    return _tts

def say(text, out, sid=5, speed=1.05, steps=10):
    g = sherpa_onnx.GenerationConfig()
    g.sid, g.num_steps, g.speed = sid, steps, speed
    g.extra["lang"] = "ko"
    a = tts().generate(text, g)
    sf.write(out, a.samples, samplerate=a.sample_rate, subtype="PCM_16")
    return len(a.samples) / a.sample_rate

if __name__ == "__main__":
    text = "안녕하세요. 우리동네 대형폐기물 수수료 확인 서비스를 소개합니다. 서울 강남구에서 3인용 소파를 버리면 수수료는 7,000원입니다."
    for sid in range(10):
        t = time.time(); d = say(text, f"sample_sid{sid}.wav", sid=sid)
        print(sid, f"{d:.1f}s audio in {time.time()-t:.1f}s")
