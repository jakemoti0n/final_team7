"""따라가기 재식별(appearance.py) 단위 시험: 깊이 마스크·밴드·서명·운용자 판정."""

import numpy as np

from limbo_perception import appearance as ap

BAND = ap.BandConfig(min_pixels=10)
IDENT = ap.IdentityConfig(hold_sec=2.0, lost_sec=5.0, gate_m=0.8)


def _hsv(h, s, v, shape=(20, 10)):
    img = np.zeros(shape + (3,), dtype=np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = h, s, v
    return img


def test_depth_mask_keeps_only_person_depth():
    depth = np.full((4, 4), 2.0)
    depth[0, 0] = 3.0          # 뒤 배경
    depth[1, 1] = np.nan
    mask = ap.depth_mask(depth, 2.0, 0.35)
    assert mask.sum() == 14 and not mask[0, 0] and not mask[1, 1]


def test_band_pixels_counts_band_color_inside_mask_only():
    hsv = _hsv(110, 200, 200)            # 청바지 색
    hsv[5:10, 2:8] = (160, 220, 230)     # 분홍 밴드 30 px
    mask = np.ones(hsv.shape[:2], dtype=bool)
    assert ap.band_pixels(hsv, mask, BAND) == 30
    mask[5:10, :] = False                # 밴드 자리가 다른 깊이(다른 사람)면 안 센다
    assert ap.band_pixels(hsv, mask, BAND) == 0


def test_signature_similarity_separates_colors():
    blue = ap.color_signature(_hsv(110, 200, 150), np.ones((20, 10), dtype=bool), BAND)
    blue2 = ap.color_signature(_hsv(112, 190, 120), np.ones((20, 10), dtype=bool), BAND)
    brown = ap.color_signature(_hsv(15, 150, 100), np.ones((20, 10), dtype=bool), BAND)
    assert ap.signature_similarity(blue, blue2) > 0.8
    assert ap.signature_similarity(blue, brown) < 0.1
    assert ap.signature_similarity(blue, None) == 0.0


def _cand(pid, x, y, band=0, sig=None, base_x=1.5, base_y=0.0):
    return ap.Candidate(pid, x, y, base_x=base_x, base_y=base_y, band_pixels=band, signature=sig)


def _sig(h):
    return ap.color_signature(_hsv(h, 200, 150), np.ones((20, 10), dtype=bool), BAND)


def test_enroll_needs_exactly_one_band_person_in_front():
    ident = ap.OperatorIdentity(BAND, IDENT)
    assert ident.decide([_cand(1, 1.5, 0.0, band=50, sig=_sig(110))], 0.0).reason == 'not_enrolled'
    ok, why = ident.enroll([_cand(1, 1.5, 0.0, band=0, sig=_sig(110))], 0.0)
    assert not ok and why == 'no_band_person_in_zone'
    ok, why = ident.enroll([_cand(1, 1.5, 0.0, band=50, sig=_sig(110)),
                            _cand(2, 2.0, 0.5, band=40, sig=_sig(110), base_x=2.0, base_y=0.5)], 0.0)
    assert not ok and why == 'multiple_band_people'
    ok, _ = ident.enroll([_cand(1, 1.5, 0.0, band=50, sig=_sig(110)),
                          _cand(2, 4.0, 0.5, band=40, sig=_sig(110), base_x=4.0)], 0.0)
    assert ok and ident.target_id == 1


def test_band_wins_over_everything_and_other_person_is_not_taken():
    ident = ap.OperatorIdentity(BAND, IDENT)
    ident.enroll([_cand(1, 1.5, 0.0, band=50, sig=_sig(110))], 0.0)
    # 다른 사람(밴드 없음, 같은 옷)이 더 가까이 와도 밴드 찬 쪽이 운용자
    d = ident.decide([_cand(7, 1.0, 0.1, band=0, sig=_sig(110)),
                      _cand(1, 2.0, 0.0, band=30, sig=_sig(110))], 0.5)
    assert d.found and d.person_id == 1 and d.reason == 'band'


def test_band_hidden_briefly_keeps_same_track_then_loses():
    ident = ap.OperatorIdentity(BAND, IDENT)
    ident.enroll([_cand(1, 1.5, 0.0, band=50, sig=_sig(110))], 0.0)
    d = ident.decide([_cand(1, 1.6, 0.0, band=0, sig=_sig(110))], 1.0)
    assert d.found and d.reason == 'track'
    # 트랙 번호가 바뀌면 옷 서명이 같아도 갈아타지 않는다 (옷이 같은 다른 사람일 수 있다) → 놓침
    d = ident.decide([_cand(9, 1.7, 0.1, band=0, sig=_sig(110))], 1.5)
    assert not d.found and d.reason == 'lost'
    # 같은 번호가 다시 보이면 이어 간다
    d = ident.decide([_cand(1, 1.7, 0.1, band=0, sig=_sig(110))], 1.8)
    assert d.found and d.reason == 'track'
    # hold_sec(2 s)가 지나면 밴드 없이는 안 믿는다
    d = ident.decide([_cand(1, 1.8, 0.1, band=0, sig=_sig(110))], 2.5)
    assert not d.found and d.reason == 'lost'
    # lost_sec(5 s)가 지나면 대상 해제, 등록은 남음
    d = ident.decide([], 7.0)
    assert d.reason == 'lost_timeout' and ident.target_id is None and ident.enrolled
    # 밴드가 다시 보이면 바로 복귀
    d = ident.decide([_cand(12, 3.0, 0.0, band=20, sig=_sig(110))], 7.5)
    assert d.found and d.reason == 'band' and d.person_id == 12


def test_same_track_with_different_clothes_is_rejected_when_band_hidden():
    ident = ap.OperatorIdentity(BAND, IDENT)
    ident.enroll([_cand(1, 1.5, 0.0, band=50, sig=_sig(110))], 0.0)
    # 같은 트랙 번호인데 옷 색이 등록과 다름(트랙이 다른 사람에게 넘어감) → 거부
    d = ident.decide([_cand(1, 1.6, 0.1, band=0, sig=_sig(15))], 0.5)
    assert not d.found and d.reason == 'signature_mismatch'
    # 다른 트랙 번호에 다른 옷 → 놓침
    d = ident.decide([_cand(5, 1.6, 0.1, band=0, sig=_sig(15))], 0.6)
    assert not d.found and d.reason == 'lost'
