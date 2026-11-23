# 방문자 안내 약도 파일

관제 화면 **약도 편집** 페이지가 저장하는 파일(`guide_yaml`)을 두는 곳이다. 좌표는 지도와 같은 m(map 프레임)이고,
지도 하나에 약도 하나다. 파일 이름은 `<지도 이름>_guide.yaml`로 맞춘다.

- 로컬 개발: `dashboard/config.json`의 `guide_yaml`이 이 폴더의 파일을 가리킨다. 화면에서 저장하면 여기 바뀌므로 커밋할 수 있다
- 클라우드(Docker): 서버는 볼륨의 `/data/guide.yaml`에 저장한다. 이 폴더의 파일은 이미지에 기본값으로 들어가며,
  `.env`의 `INITIAL_GUIDE`로 고르면 처음 시작 때만 복사된다. 클라우드에서 고친 약도는 편집 화면의 **내려받기**로 받아 여기 커밋한다

약도를 그림 파일로 쓰면 그림은 `<약도 이름>_files/`(예: `human_test_map_guide_files/`)에 저장된다. 커밋할 때 이 폴더도 같이 올린다.
클라우드에서는 그림이 `/data/guide_files/`에 있으므로 `docker compose cp dashboard:/data/guide_files ./`로 받는다.

형식은 `dashboard/server/guide.py` 맨 위 설명을 본다.

## 하단 디스플레이 내용 (`display/`)

로봇 하단 디스플레이(`/display`)에 보일 행사 일정·문구·팜플렛을 `display/`에 둔다(`display_dir`).
`display.json` 하나와 팜플렛 그림(PNG·JPEG·WebP, 1920×1080 권장)을 넣고, 보여 줄 그림 이름을 `display.json`의 `slides`에 적는다.
형식은 `dashboard/server/display.py` 맨 위 설명을 본다. 파일을 바꾸면 서버를 다시 켜지 않아도 반영된다. 잘못 고치면 마지막 정상본을 계속 쓰고 서버 로그에 이유를 남긴다.

**「LIMBO가 지나갑니다」 소리**: 로봇이 순찰 중 출발할 때 화면과 함께 한 번 튼다. 기본으로 `passing.mp3`(Google 번역 TTS로 만든 4초짜리)가 들어 있다.
다른 목소리로 바꾸려면 TTS로 만든 MP3·WAV·OGG(2 MB 이하) 파일을 이 폴더에 넣고 `display.json`의 `"sound"`에 이름을 적는다(같은 이름으로 덮어써도 된다). 문장은 `림보가 지나갑니다. 길을 조금 비켜 주세요.`
(「LIMBO」를 영어 철자로 읽지 않게 한글로 쓴다). 아무 한국어 TTS(클라우드 TTS 서비스, 휴대폰·PC의 읽어 주기 녹음 등)로 만들면 된다.
파일이 없으면 브라우저에 한국어 음성이 있을 때만 그 음성으로 읽고, 없으면 화면만 띄운다.

- 로컬 개발: `dashboard/config.json`의 `display_dir`이 이 폴더를 가리킨다
- 클라우드(Docker): 볼륨의 `/data/display/`를 쓴다. 처음 시작 때만 이 폴더가 복사된다. 바꿀 때는
  `docker compose cp display.json dashboard:/data/display/display.json`처럼 넣는다(그림·소리도 같은 방법)
