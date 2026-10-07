"""사람 위치 추적용 등속(constant velocity) 칼만 필터."""

import numpy as np

INITIAL_COVARIANCE = 1.0


class PersonKalmanFilter:
    """상태 [x, y, vx, vy], 측정 [x, y]인 2D 등속 모델 칼만 필터."""

    def __init__(self, x, y, measurement_noise=0.05, process_noise=0.5):
        self.x = np.array([[x], [y], [0.0], [0.0]], dtype=float)

        self.P = np.eye(4) * INITIAL_COVARIANCE

        # 카메라로는 위치만 재고 속도는 측정하지 않는다
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
        ])

        # RGB-D + YOLO 위치가 흔들리는 정도
        self.R = np.eye(2) * measurement_noise

        self.process_noise = process_noise

    def predict(self, dt):
        self.F = np.array([
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ])

        self.Q = np.array([
            [dt**4 / 4, 0.0, dt**3 / 2, 0.0],
            [0.0, dt**4 / 4, 0.0, dt**3 / 2],
            [dt**3 / 2, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2, 0.0, dt**2],
        ]) * self.process_noise

        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q

    def update(self, measured_x, measured_y):
        z = np.array([[measured_x], [measured_y]])

        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)

        self.x = self.x + K @ y
        self.P = (np.eye(4) - K @ self.H) @ self.P

    def get_state(self):
        """(x, y, vx, vy)를 float로 반환한다."""
        return (
            float(self.x[0, 0]),
            float(self.x[1, 0]),
            float(self.x[2, 0]),
            float(self.x[3, 0]),
        )
