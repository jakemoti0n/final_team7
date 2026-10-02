"""limbo_perception 패키지."""

import os

# PyTorch(OpenMP)와 numpy(OpenBLAS)가 각자 코어 수(16)만큼 스레드를 띄워 서로 기다리며
# 헛돌아서, 시뮬레이션 중 person_detector가 CPU 8코어(775%)를 쓰고 있었다.
# 스레드 풀 크기는 numpy/torch를 import할 때 정해지므로 패키지가 처음 로드될 때 설정한다.
# 실행할 때 환경변수로 따로 지정하면 그 값을 우선한다.
CPU_THREADS = '2'
os.environ.setdefault('OMP_NUM_THREADS', CPU_THREADS)
os.environ.setdefault('OPENBLAS_NUM_THREADS', CPU_THREADS)
