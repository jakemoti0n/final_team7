# 관제 화면 글꼴 파일

| 파일 | 원본 | 가공 |
|---|---|---|
| `GmarketSansBold.subset.woff2` | `https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/GmarketSansBold.woff` (Stitch 시안이 쓰던 파일, 약 615 KB) | 약 120 KB |
| `GmarketSansMedium.subset.woff2` | 같은 곳의 `GmarketSansMedium.woff` (약 596 KB) | 약 125 KB |

- 가공: fontTools로 **ASCII + KS X 1001 완성형 한글 2,350자 + `·…→←↑↓‘’“”–—×°±※`** 만 남기고 woff2로 바꿨다. 빠진 글자(드문 한글 등)는 CSS의 다음 글꼴(Pretendard)로 그려진다.
- 다시 만들기: 글자 목록 = `bytes([b1, b2]).decode('euc-kr')` (b1 0xB0–0xC8, b2 0xA1–0xFE) + ASCII + 위 기호
  `python -m fontTools.subset GmarketSansBold.woff --text-file=glyphs.txt --flavor=woff2 --layout-features='*' --output-file=GmarketSansBold.subset.woff2`
- 라이선스: Gmarket Sans는 G마켓이 무료로 배포하는 글꼴이다. Gmarket Sans는 'SIL Open Font License'에 따라 개인 또는 기업이 영리적, 비영리적 목적으로 자유롭게 사용할 수 있다.
- Pretendard(OFL-1.1)와 JetBrains Mono(OFL-1.1)는 npm 패키지(`pretendard`, `@fontsource/jetbrains-mono`)로 들어오며 이 폴더에 없다.
