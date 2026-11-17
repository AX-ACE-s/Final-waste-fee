# 시연 영상 녹화 도구

실제 화면을 브라우저로 자동 조작하며 녹화하고, 화면 아래에 자막을 띄운 mp4를 만듭니다(음성 없음, 약 4분 30초).

```bash
pip install playwright
python -m playwright install chromium
# ffmpeg 도 필요합니다 (없으면 .webm 으로 저장)

python app.py                          # 다른 창에서 서버 켜 두기
python tools/demo_video/record.py      # -> tools/demo_video/demo.mp4
python tools/demo_video/record.py --photo 소파사진.jpg   # 실제 AI 인식을 보여 줄 사진
```

- `.env`에 `ANTHROPIC_API_KEY`가 있으면 실제 AI 사진 인식이, `JUSO_API_KEY`가 있으면 도로명주소 검색(‘강서구청’)이 영상에 나옵니다. 키 값은 화면에 나오지 않습니다.
- 키가 없으면 사진 인식은 연습용 응답으로 녹화되고 자막에 그 사실이 표시됩니다.
- `sample_sofa.jpg`는 그림으로 그린 예시 사진입니다. 실제 AI 인식을 보여 줄 때는 진짜 소파 사진을 `--photo`로 넣으세요.
- 결과물(`demo.mp4`, `work/`)은 저장소에 올리지 않습니다(.gitignore).
