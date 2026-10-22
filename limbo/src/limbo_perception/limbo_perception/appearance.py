"""
따라가기(운용자 재식별)용 겉모습 계산과 판정 (ROS 의존 없음).

운용자는 미리 정해진 한 사람(직원)이고, 발목·종아리에 두른 형광 밴드가 주 근거다 (PROJECT.md 2-9).
  1. 깊이 마스크: 박스 안에서 측정한 사람 거리 ± depth_tol 안의 픽셀만 그 사람으로 본다 (세그멘테이션 역할).
     앞사람 박스에 뒤에 선 운용자의 밴드가 끼어 들어도 깊이가 달라 걸러진다.
  2. 밴드: 마스크 안에서 밴드 색(HSV 범위) 픽셀 수. min_pixels 이상이면 운용자로 확인.
  3. 트랙 연속성: 밴드가 잠깐 가려지면 hold_sec 동안 같은 트랙 번호(외삽 위치 gate_m 안)만 믿는다.
  4. 서명: 마스크 안 하반신 색 분포(H×S 히스토그램). 같은 트랙 번호라도 등록 때와 옷 색이 다르면 거부한다.
     서명으로 다른 트랙에 갈아타지는 않는다(옷이 같은 사람끼리는 못 가름).
어느 것도 안 맞으면 "놓침"이다. 잘못 따라가느니 멈추는 쪽을 택한다.
"""

from dataclasses import dataclass
import math
from typing import Optional

import numpy as np


@dataclass
class BandConfig:
    # OpenCV HSV (H 0~179). 기본은 분홍·자홍 형광 밴드: 피부색·바지(청색)·실내 벽과 겹치지 않는다
    hue_min: int = 140
    hue_max: int = 175
    sat_min: int = 100
    val_min: int = 80
    min_pixels: int = 10          # 320×240에서 4~5 m의 밴드 하나가 20~40 px
    depth_tol: float = 0.35       # m, 사람 깊이 ± 이 안만 그 사람의 픽셀로 본다
    signature_bins: tuple = (8, 4)  # H, S 칸 수


@dataclass
class IdentityConfig:
    signature_min: float = 0.6    # 같은 트랙을 이어 믿을 때 요구하는 서명 유사도 (0~1). 이보다 낮으면 거부
    hold_sec: float = 2.0         # 밴드 없이 같은 트랙 번호만으로 버티는 시간
    lost_sec: float = 5.0         # 이 시간 넘게 못 찾으면 대상 해제 (등록은 유지)
    gate_m: float = 0.8           # 외삽 위치에서 이 거리 안의 트랙만 후보
    enroll_min_x: float = 0.5     # 등록은 로봇 앞 이 범위 안의 밴드 찬 사람 (base_link 기준, m)
    enroll_max_x: float = 2.5
    enroll_half_width: float = 0.8
    signature_update: float = 0.05  # 밴드로 확인된 프레임마다 서명을 이만큼 섞어 갱신 (조명 변화 적응)


@dataclass
class Candidate:
    """한 프레임의 사람 트랙 하나 (odom 위치, base_link 위치, 겉모습)."""
    person_id: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    base_x: float = 0.0
    base_y: float = 0.0
    band_pixels: int = 0
    signature: Optional[np.ndarray] = None


@dataclass
class Decision:
    enrolled: bool
    found: bool
    reason: str                  # band | band_multi | track | signature_mismatch | lost | lost_timeout | not_enrolled
    person_id: int = -1
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    band_pixels: int = 0
    similarity: float = 0.0
    since_band_sec: float = 0.0
    lost_sec: float = 0.0


def depth_mask(depth_roi, person_depth, tol):
    """사람 깊이 ± tol 안의 유효 픽셀 마스크. depth_roi는 m 단위 2차원 배열."""
    finite = np.isfinite(depth_roi)
    return finite & (np.abs(depth_roi - person_depth) <= tol)


def band_pixels(hsv_roi, mask, config):
    """마스크 안에서 밴드 색 픽셀 수."""
    if hsv_roi.size == 0 or not mask.any():
        return 0
    h, s, v = hsv_roi[..., 0], hsv_roi[..., 1], hsv_roi[..., 2]
    hit = (h >= config.hue_min) & (h <= config.hue_max) & \
          (s >= config.sat_min) & (v >= config.val_min) & mask
    return int(np.count_nonzero(hit))


def color_signature(hsv_roi, mask, config):
    """마스크 안 픽셀의 H×S 정규화 히스토그램. 채도 낮은(무채색) 픽셀은 H가 무의미해 S축이 따로 담는다. 픽셀이 없으면 None."""
    if hsv_roi.size == 0:
        return None
    pixels = hsv_roi[mask]
    if len(pixels) < 10:
        return None
    hb, sb = config.signature_bins
    # 픽셀 하나를 이웃한 두 칸에 거리 비례로 나눠 넣는다(선형 보간). 칸 경계에 걸친 색이 조명 변화로
    # 옆 칸으로 넘어가도 유사도가 뚝 떨어지지 않는다. H는 원형(179 다음이 0)
    h_pos = pixels[:, 0].astype(np.float32) / 180.0 * hb - 0.5
    s_pos = np.clip(pixels[:, 1].astype(np.float32) / 256.0 * sb - 0.5, 0.0, sb - 1.0)
    h0 = np.floor(h_pos).astype(int)
    s0 = np.floor(s_pos).astype(int)
    wh1 = h_pos - h0
    ws1 = s_pos - s0
    hist = np.zeros((hb, sb), dtype=np.float32)
    for dh, wh in ((0, 1.0 - wh1), (1, wh1)):
        for ds, ws in ((0, 1.0 - ws1), (1, ws1)):
            np.add.at(hist, ((h0 + dh) % hb, np.minimum(s0 + ds, sb - 1)), wh * ws)
    total = hist.sum()
    if total <= 0:
        return None
    return (hist / total).ravel()


def signature_similarity(a, b):
    """히스토그램 교집합 (0~1). 둘 중 하나라도 없으면 0."""
    if a is None or b is None or a.shape != b.shape:
        return 0.0
    return float(np.minimum(a, b).sum())


class OperatorIdentity:
    """등록한 운용자를 매 프레임 후보 트랙 중에서 고른다."""

    def __init__(self, band_config, identity_config, signature=None):
        self.band = band_config
        self.config = identity_config
        self.signature = signature          # 등록한 서명 (None이면 미등록)
        self.target_id = None
        self.last_x = self.last_y = 0.0
        self.last_vx = self.last_vy = 0.0
        self.last_time = None               # 마지막으로 찾은 시각
        self.last_band_time = None          # 마지막으로 밴드로 확인한 시각

    @property
    def enrolled(self):
        return self.signature is not None

    def enroll(self, candidates, current_time):
        """
        로봇 앞 등록 구역 안에서 밴드를 찬 사람을 운용자로 등록한다.

        성공하면 (True, 사유), 실패하면 (False, 사유). 구역에 밴드 찬 사람이 둘이면 거절한다 (한 명만 서 달라고 안내).
        """
        c = self.config
        in_zone = [k for k in candidates
                   if k.band_pixels >= self.band.min_pixels and k.signature is not None
                   and c.enroll_min_x <= k.base_x <= c.enroll_max_x
                   and abs(k.base_y) <= c.enroll_half_width]
        if not in_zone:
            return False, 'no_band_person_in_zone'
        if len(in_zone) > 1:
            return False, 'multiple_band_people'
        k = in_zone[0]
        self.signature = k.signature.copy()
        self._accept(k, current_time, band=True)
        return True, f'enrolled person {k.person_id}, band {k.band_pixels} px'

    def forget(self):
        self.signature = None
        self.target_id = None
        self.last_time = self.last_band_time = None

    def decide(self, candidates, current_time):
        """이번 프레임의 운용자. 밴드 → (hold_sec 안) 같은 트랙 번호(서명이 맞을 때만) → 놓침 순으로 본다."""
        if not self.enrolled:
            return Decision(enrolled=False, found=False, reason='not_enrolled')

        banded = [k for k in candidates if k.band_pixels >= self.band.min_pixels]
        if banded:
            k = self._closest_to_last(banded) if self.last_time is not None else \
                min(banded, key=lambda k: math.hypot(k.base_x, k.base_y))
            self._accept(k, current_time, band=True)
            self._blend_signature(k.signature)
            return self._decision(k, 'band' if len(banded) == 1 else 'band_multi', current_time)

        # 밴드가 안 보이면 hold_sec 동안 "같은 트랙 번호"만 믿는다. 서명이 비슷하다고 다른 트랙으로 갈아타지 않는다:
        # 옷이 같은 사람(유니폼 직원, 시뮬 actor)이 옆을 지나면 서명으로는 못 가르고, 1회차에서 바꿔치기 7건이 전부 그 규칙이었다.
        # 서명은 거부 용도다. 같은 번호라도 옷 색이 등록과 다르면(트랙이 다른 사람에게 넘어감) 놓침으로 본다
        if self.last_time is not None and self.last_band_time is not None \
                and current_time - self.last_band_time <= self.config.hold_sec:
            same = [k for k in candidates
                    if k.person_id == self.target_id and self._within_gate(k, current_time)]
            if same:
                k = same[0]
                s = signature_similarity(self.signature, k.signature)
                if k.signature is None or s >= self.config.signature_min:
                    self._accept(k, current_time, band=False)
                    return self._decision(k, 'track', current_time, similarity=s)
                reason = 'signature_mismatch'
                return Decision(enrolled=True, found=False, reason=reason, person_id=k.person_id,
                                similarity=s, since_band_sec=self._since_band(current_time),
                                lost_sec=current_time - self.last_time, x=self.last_x, y=self.last_y)

        lost = 0.0 if self.last_time is None else current_time - self.last_time
        if self.target_id is not None and lost > self.config.lost_sec:
            self.target_id = None
            reason = 'lost_timeout'
        else:
            reason = 'lost'
        return Decision(enrolled=True, found=False, reason=reason, lost_sec=lost,
                        since_band_sec=self._since_band(current_time),
                        x=self.last_x, y=self.last_y)

    def _within_gate(self, k, current_time):
        age = current_time - self.last_time
        px = self.last_x + self.last_vx * age
        py = self.last_y + self.last_vy * age
        return math.hypot(k.x - px, k.y - py) <= self.config.gate_m

    def _closest_to_last(self, candidates):
        return min(candidates, key=lambda k: math.hypot(k.x - self.last_x, k.y - self.last_y))

    def _accept(self, k, current_time, band):
        self.target_id = k.person_id
        self.last_x, self.last_y = k.x, k.y
        self.last_vx, self.last_vy = k.vx, k.vy
        self.last_time = current_time
        if band:
            self.last_band_time = current_time

    def _blend_signature(self, signature):
        if signature is None or self.signature is None or signature.shape != self.signature.shape:
            return
        a = self.config.signature_update
        self.signature = (1.0 - a) * self.signature + a * signature

    def _since_band(self, current_time):
        return 0.0 if self.last_band_time is None else current_time - self.last_band_time

    def _decision(self, k, reason, current_time, similarity=None):
        if similarity is None:
            similarity = signature_similarity(self.signature, k.signature)
        return Decision(enrolled=True, found=True, reason=reason, person_id=k.person_id,
                        x=k.x, y=k.y, vx=k.vx, vy=k.vy, band_pixels=k.band_pixels,
                        similarity=similarity, since_band_sec=self._since_band(current_time))
