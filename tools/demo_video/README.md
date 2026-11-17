# 시연 영상 만들기 (자동 녹화 + TTS)

대본(`script.py`) → 문장별 한국어 음성 생성 → 앱을 자동 조작하며 1080p 녹화 → 음성·자막 합성 → `demo.mp4`.
말과 화면이 어긋나지 않도록, 화면 조작이 늦으면 다음 문장이 기다립니다.

## 준비

```bash
pip install sherpa-onnx soundfile numpy pillow playwright
# 오프라인 한국어 TTS (Supertonic 3, MIT) / 발음 검증용 음성인식
mkdir -p models && cd models
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-zipformer-korean-2024-06-24.tar.bz2
tar xjf sherpa-onnx-supertonic-3-tts-int8-2026-05-11.tar.bz2 && tar xjf sherpa-onnx-zipformer-korean-2024-06-24.tar.bz2
```

ffmpeg(libass 포함), 한글 글꼴(Noto Sans CJK KR)이 필요합니다.

## 실행 (앱을 먼저 `python app.py`로 켜 둔 상태에서)

```bash
python build.py tts      # 음성 생성 + 음성인식으로 발음 검증 (불일치 문장 출력)
python build.py record   # 127.0.0.1:5000 자동 조작 녹화 → work/screen.mp4
python build.py mux      # 음성·자막 합성 → demo.mp4
```

대본·화면 조작을 바꾸려면 `script.py`, 제목 카드는 `cards.py`를 고치면 됩니다.
