"""person_filter: 사람 트랙 반경 안의 점을 점구름에서 뺀다 (설계 전제 2-8 규칙 1)."""

from limbo_perception import person_filter as pf
import numpy as np
from sensor_msgs.msg import PointCloud2, PointField


def _cloud(points, extra=True):
    """x·y·z(+intensity) float32 점구름. 바이트 행 복사가 다른 필드를 보존하는지 보려고 intensity를 둔다."""
    msg = PointCloud2()
    msg.fields = [PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
                  PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
                  PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1)]
    if extra:
        msg.fields.append(
            PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1))
    msg.point_step = 16 if extra else 12
    rows = [(p + ((float(i),) if extra else ())) for i, p in enumerate(points)]
    arr = np.array(rows, dtype=np.float32)
    msg.height, msg.width = 1, len(points)
    msg.row_step = msg.point_step * msg.width
    msg.data = arr.tobytes()
    return msg


def test_points_inside_person_radius_are_removed_and_others_kept():
    """사람(2,0) 반경 0.5 m 안의 점만 빠지고 벽·상자 점은 남는다."""
    pts = np.array([[2.0, 0.1, 0.5], [2.3, -0.2, 0.9], [4.0, 0.0, 0.3], [0.0, 0.0, 0.1]])
    mask = pf.people_mask(pts, np.array([[2.0, 0.0]]), 0.5)
    assert mask.tolist() == [False, False, True, True]


def test_no_people_keeps_everything():
    """사람이 없으면 아무 점도 빼지 않는다."""
    pts = np.array([[1.0, 0.0, 0.0]])
    assert pf.people_mask(pts, np.zeros((0, 2)), 0.5).tolist() == [True]


def test_keep_rows_preserves_other_fields_and_byte_layout():
    """남긴 점의 intensity 등 다른 필드가 그대로이고 폭·row_step이 맞는다."""
    msg = _cloud([(1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (3.0, 0.0, 0.0)])
    out = pf.keep_rows(msg, np.array([True, False, True]))
    assert out.width == 2 and out.row_step == 32 and out.point_step == 16
    arr = np.frombuffer(out.data, dtype=np.float32).reshape(-1, 4)
    assert arr[:, 0].tolist() == [1.0, 3.0] and arr[:, 3].tolist() == [0.0, 2.0]


def test_xyz_view_reads_by_field_offset():
    """x·y·z는 필드 오프셋으로 읽는다(필드 순서·여분 필드와 무관)."""
    msg = _cloud([(1.0, 2.0, 3.0)])
    xyz = pf.xyz_view(msg)
    assert xyz.shape == (1, 3) and xyz[0].tolist() == [1.0, 2.0, 3.0]
