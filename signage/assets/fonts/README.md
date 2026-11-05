# 글꼴

이 폴더의 `.ttf` / `.otf` / `.ttc` 파일은 앱이 시작할 때 자동 등록된다.
쓸 글꼴은 `config/app.yaml`의 `theme.font_families` 목록에서 **설치된 첫 이름**이 선택된다.

라즈베리파이 기본 한글 글꼴이 투박해 보일 수 있으므로(PPT 2페이지) 원하는 글꼴을 여기에 넣는다. 예:

- Pretendard (SIL OFL): `Pretendard-Regular.otf`, `Pretendard-Bold.otf`를 넣으면 목록 첫 이름 `Pretendard`가 선택된다.
- 아무것도 넣지 않으면 시스템의 `Noto Sans CJK KR`(`sudo apt install fonts-noto-cjk`) 등을 쓴다.

글꼴 라이선스(배포 허용 여부)를 확인한 뒤 넣는다. 글꼴을 바꾼 뒤에는 앱을 다시 시작한다.
