from pathlib import Path
import math
import yaml
from ultralytics import YOLO
# A-1은 읽기만 하고 수정하지 않습니다.
a1_dir = Path(
    "/data/recycle_dataset/notebooks/model A/runs/recycle_yolo11n_14class_v1"
)
best_pt = a1_dir / "weights" / "best.pt"
args_path = a1_dir / "args.yaml"
# A-2는 반드시 별도 폴더에 저장합니다.
project = Path("/data/recycle_dataset/notebooks/model A/runs")
name = "recycle_yolo11n_14class_A-2"
a2_dir = project / name
if not best_pt.is_file():
    raise FileNotFoundError(best_pt)
if not args_path.is_file():
    raise FileNotFoundError(args_path)
if a2_dir.exists():
    raise FileExistsError(f"A-2 폴더가 이미 있습니다. 덮어쓰지 않습니다: {a2_dir}")
args = yaml.safe_load(args_path.read_text(encoding="utf-8"))
data_yaml = Path(args["data"])
if not data_yaml.is_file():
    raise FileNotFoundError(data_yaml)
# Ultralytics가 best.pt를 선택할 때 사용하는 검증 fitness의 최고 기록
state = {"best_fitness": float("-inf"), "best_epoch": 0}
def stop_after_minimum_30(trainer):
    # 이 콜백은 매 epoch의 검증과 체크포인트 저장 후에 실행됩니다.
    # 학습 종료 후 최종 best.pt 재검증 때도 호출될 수 있으므로 건너뜁니다.
    if trainer.stop:
        return
    fitness = trainer.fitness
    if fitness is None:
        return
    fitness = float(fitness)
    if not math.isfinite(fitness):
        return
    epoch = trainer.epoch + 1  # 사람에게 보이는 1부터 시작하는 epoch 번호
    if fitness > state["best_fitness"]:
        state["best_fitness"] = fitness
        state["best_epoch"] = epoch
    # 30 epoch까지는 무조건 학습합니다.
    # 이후에는 30 epoch 또는 마지막 최고점 중 더 늦은 시점부터 20 epoch를 셉니다.
    patience_start = max(30, state["best_epoch"])
    if epoch >= 30 and epoch - patience_start >= 20:
        print(
            f"사용자 지정 조기 종료: {epoch} epoch 완료, "
            f"마지막 최고점은 {state['best_epoch']} epoch"
        )
        trainer.stop = True
model = YOLO(str(best_pt))
model.add_callback("on_fit_epoch_end", stop_after_minimum_30)
model.train(
    data=str(data_yaml),
    optimizer="MuSGD",  # A-1 로그에서 실제 선택된 optimizer
    lr0=0.003,          # A-1의 실제 0.01보다 낮게 시작
    momentum=0.9,
    imgsz=640,
    batch=64,
    epochs=100,         # 절대 상한
    patience=0,         # 기본 조기 종료는 끄고 위 콜백으로 제어
    val=True,           # 매 epoch 검증 지표가 필요
    save=True,
    project=str(project),
    name=name,
    exist_ok=False,
    resume=False,
    device=args["device"],                 # '0'
    workers=args["workers"],               # 4
    seed=args["seed"],                     # 42
    deterministic=args["deterministic"],   # True
    amp=args["amp"],     
)