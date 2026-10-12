from pathlib import Path
from ultralytics import YOLO

# =========================================================
# 경로
# =========================================================

WORK_DIR = Path("/data/recycle_dataset/notebooks/model A")

# 기존 12클래스 YOLO11n 모델
MODEL_PATH = Path(
    "/data/yolo_runs/recycle_yolo11n/weights/best.pt"
)

# 새로 만든 14클래스 데이터셋
DATA_PATH = Path(
    "/data/recycle_dataset/model_a_stage1_14class_27500_v1/data.yaml"
)

# 학습 결과 저장 폴더
RUNS_DIR = WORK_DIR / "runs"


# =========================================================
# 파일 확인
# =========================================================

if not MODEL_PATH.exists():
    raise FileNotFoundError(
        f"기존 모델 없음: {MODEL_PATH}"
    )

if not DATA_PATH.exists():
    raise FileNotFoundError(
        f"data.yaml 없음: {DATA_PATH}"
    )

RUNS_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# 기존 모델 불러오기
# =========================================================

model = YOLO(str(MODEL_PATH))

print("기존 모델:")
print(MODEL_PATH)

print("\n기존 클래스:")
print(model.names)

print("\n새 데이터셋:")
print(DATA_PATH)


# =========================================================
# 추가 학습
# =========================================================

results = model.train(

    # 데이터
    data=str(DATA_PATH),

    # 학습 횟수
    epochs=50,

    # 입력 크기
    imgsz=640,

    # V100 32GB 기준
    batch=64,

    # GPU
    device=0,

    # 서버 CPU 4코어
    workers=4,

    # 10 epoch 동안 개선 없으면 종료
    patience=10,

    # Ultralytics 자동 optimizer
    optimizer="auto",

    # Mixed Precision
    amp=True,

    # 재현성
    seed=42,
    deterministic=True,

    # RAM 캐시 사용 안 함
    cache=False,

    # 결과 저장
    project=str(RUNS_DIR),
    name="recycle_yolo11n_14class_v1",

    save=True,

    # 5 epoch마다 checkpoint
    save_period=5,

    verbose=True,
)


# =========================================================
# 완료
# =========================================================

print("\n학습 완료")

print(
    "결과 폴더:",
    RUNS_DIR / "recycle_yolo11n_14class_v1"
)

print(
    "Best 모델:",
    RUNS_DIR /
    "recycle_yolo11n_14class_v1" /
    "weights" /
    "best.pt"
)