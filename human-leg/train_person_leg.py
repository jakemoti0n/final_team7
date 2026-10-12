"""roboflow_leg 데이터로 사람(person)·다리(leg) YOLO 모델을 초기 학습한다.

이 파일을 /data/human/train_person_leg.py에 놓고, 서버 가상환경에서
    cd /data/human
    python train_person_leg.py
로 실행한다. CUDA GPU와 torch·ultralytics가 필요하다.
두 번째 데이터(coco_lower)와 기존 라벨 파일은 수정하지 않는다.
"""

# 파일 위치와 폴더 경로를 운영체제에 맞게 다루기 위한 표준 라이브러리이다.
from pathlib import Path


class StopAfter80:
    """80회까지 학습하고, 이후 검증 성능이 10회 연속 개선되지 않으면 중단."""

    def __init__(self):
        self.best_after_80 = None  # 80회째 검증 성능을 비교 기준으로 저장한다.
        self.no_improvement = 0  # 기준보다 나아지지 않은 연속 횟수이다.

    def __call__(self, trainer):
        epoch = trainer.epoch + 1  # Ultralytics의 0부터 시작하는 번호를 1부터 센다.
        if epoch < 80 or trainer.fitness is None:  # 80회 전에는 중단하지 않는다.
            return
        fitness = float(trainer.fitness)  # 검증 성능을 숫자로 읽는다.
        if epoch == 80:  # 80회째 성능을 초기 기준으로 삼는다.
            self.best_after_80 = fitness
            print(f"80회 완료: 기준 검증 성능={fitness:.6f}", flush=True)
        elif fitness > self.best_after_80:  # 이후 더 좋은 성능이면 대기 횟수를 초기화한다.
            self.best_after_80 = fitness
            self.no_improvement = 0
            print(f"{epoch}회: 검증 성능 개선={fitness:.6f}", flush=True)
        else:  # 개선되지 않았다면 연속 횟수를 하나 올린다.
            self.no_improvement += 1
            print(f"{epoch}회: 개선 없음 ({self.no_improvement}/10)", flush=True)
            if self.no_improvement >= 10:  # 80회 이후 10회 연속 개선이 없으면 중단한다.
                trainer.stop = True
                print(f"{epoch}회 종료: 검증 성능 10회 연속 개선 없음", flush=True)


def main():
    # 이 스크립트가 놓인 폴더를 작업 기준으로 삼는다(예: /data/human).
    root = Path(__file__).resolve().parent
    # 첫 번째 학습 데이터셋의 폴더를 지정한다.
    dataset = root / "roboflow_leg"

    # 학습·검증·최종 시험 데이터의 이미지/라벨 폴더를 모두 확인한다.
    for split in ("train", "valid", "test"):
        images = dataset / split / "images"  # 이 분할의 이미지 폴더
        labels = dataset / split / "labels"  # 이 분할의 YOLO 형식 라벨 폴더
        if not images.is_dir() or not labels.is_dir():  # 폴더가 없으면 학습 전 중단
            raise FileNotFoundError(f"이미지 또는 라벨 폴더가 없습니다: {images}, {labels}")
        # 이미지 파일과 라벨 TXT 파일의 개수를 각각 센다.
        image_count = sum(p.suffix.lower() in {".jpg", ".jpeg", ".png"} for p in images.iterdir())
        label_count = sum(p.suffix.lower() == ".txt" for p in labels.iterdir())
        print(f"{split}: 이미지={image_count}, 라벨={label_count}", flush=True)  # 확인 결과 표시
        if image_count == 0 or image_count != label_count:  # 누락 또는 개수 불일치 검사
            raise ValueError(f"{split}의 이미지·라벨 개수가 맞지 않습니다")

    # 설치된 가상환경의 PyTorch와 Ultralytics YOLO를 불러온다.
    import torch
    from ultralytics import YOLO

    # 이 스크립트는 GPU 학습용이므로 CUDA가 보이지 않으면 시작하지 않는다.
    if not torch.cuda.is_available():
        raise RuntimeError("현재 Python 환경에서 CUDA GPU가 보이지 않아 학습을 시작하지 않았습니다")
    print(f"사용 GPU: {torch.cuda.get_device_name(0)}", flush=True)  # 사용할 GPU 이름 표시

    # 원본 data.yaml 대신, 실제 서버 경로가 들어간 학습 설정 파일을 만든다.
    config = root / "person_leg_stage1.yaml"
    config.write_text(
        f"path: {dataset.as_posix()}\n"  # 데이터셋의 절대경로
        "train: train/images\n"  # 모델 가중치를 학습할 이미지
        "val: valid/images\n"  # 학습 중 성능을 평가할 이미지
        "test: test/images\n"  # 추후 독립적인 최종 평가에 사용할 이미지
        "names:\n"  # 클래스 번호와 이름의 대응 관계
        "  0: person\n"  # 기존 사람 라벨: 0번
        "  1: leg\n",  # 기존 다리 라벨: 1번
        encoding="utf-8",  # 설정 파일을 UTF-8로 저장
    )

    # 사전 학습된 YOLO11 nano 모델에서 출발한다(없으면 다운로드가 필요할 수 있다).
    model = YOLO("yolo11n.pt")
    # 매 회 검증이 끝날 때 사용자 지정 80+10 조기 종료 조건을 확인한다.
    model.add_callback("on_fit_epoch_end", StopAfter80())
    # 첫 번째 데이터셋만 사용해 person·leg 두 클래스를 학습한다.
    model.train(
        data=str(config),  # 위에서 만든 데이터셋 설정 파일
        epochs=200,  # 최대 200회 반복하며, 80회 이후에는 아래 조건으로 조기 종료
        imgsz=640,  # 학습 입력 이미지 크기
        batch=-1,  # V100의 사용 가능한 메모리를 고려하여 배치 크기를 자동 선택
        device=0,  # 첫 번째 CUDA GPU(V100) 사용
        workers=4,  # 데이터 읽기에 사용할 작업 프로세스 수
        patience=0,  # 기본 조기 종료를 끄고 위의 80회 이후 조건만 적용
        save_period=10,  # 80회째 모델도 별도 체크포인트로 보관
        project=str(root / "runs"),  # 학습 결과가 저장될 상위 폴더
        name="person_leg_stage1",  # 이번 학습 결과 폴더 이름
        exist_ok=False,  # 같은 이름이 있으면 덮어쓰지 않고 새 폴더 생성
    )
    # 실제 학습 결과 폴더에서 최상의 가중치 파일 경로를 만든다.
    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    print(f"최적 모델: {best} (파일 존재: {best.is_file()})", flush=True)  # 결과 확인


# 이 파일을 직접 실행할 때만 main()을 호출한다(다른 파일에서 가져오면 실행 안 함).
if __name__ == "__main__":
    main()
