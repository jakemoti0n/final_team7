"""'옆에서 와서 진로 위에 서는 사람'을 moving_obstacles.py에 한 유형(stand)으로 더해 띄운다.

stand: waypoints[0](진로 옆 대기 자리)에 있다가 로봇이 waypoints[1](진로 위 설 자리)에서 trigger m 안에 들어오면
그 자리로 걸어 들어가 wait초 서 있고, 다시 대기 자리로 비킨다. 로봇이 trigger + 1 m 밖으로 멀어지면 다시 준비.
로봇을 피하지 않는다(no_yield처럼 로봇 반발 없음). 카메라가 보기 전에 측면에서 들어와 서는 사람이라
'다가옴'(진로 위로 다가오는 속도)으로는 안 잡히고 코앞 막힘(ToF + 라이다 덩어리)으로만 잡힌다.

사용법: stand_mover.py <zz_stand_people.json>  (launch의 movers 대신 run.sh가 따로 띄운다)
"""
import math
import os
import sys

sys.path.insert(0, os.path.expanduser('~/limbo/limbo/install/limbo_simulation/share/limbo_simulation/scripts'))
import moving_obstacles as mo  # noqa: E402

ARRIVED = 0.1   # m, 설 자리·대기 자리에 닿았다고 보는 거리


class StandPerson(mo.Person):

    def __init__(self, spec):
        super().__init__(spec)
        self.trigger = spec.get('trigger', 2.0)
        self.home, self.spot = self.waypoints[0], self.waypoints[1]
        self.state = 'home'      # home → enter → stand → leave → home
        self.armed = True
        self.until = None

    def _say(self, text, t, robot):
        d = math.dist(robot, self.spot) if robot else float('nan')
        print(f'{self.name}: {text} (t={t:.1f}, 로봇-설 자리 {d:.2f} m)', flush=True)

    def step(self, dt, t, robot, others, walls):
        if self.type != 'stand':
            return super().step(dt, t, robot, others, walls)
        near = robot is not None and math.dist(robot, self.spot) < self.trigger
        if self.state == 'home':
            if robot is not None and math.dist(robot, self.spot) > self.trigger + 1.0:
                self.armed = True
            if self.armed and near:
                self.state, self.armed = 'enter', False
                self._say('진로로 들어감', t, robot)
        target = {'enter': self.spot, 'leave': self.home}.get(self.state)
        if target is not None and math.dist((self.x, self.y), target) < ARRIVED:
            self.x, self.y = target
            if self.state == 'enter':
                self.state, self.until = 'stand', t + self.wait
                self._say(f'진로 위에 섬 ({self.wait:.0f} s)', t, robot)
            else:
                self.state = 'home'
                self._say('대기 자리로 돌아옴', t, robot)
            target = None
        if self.state == 'stand' and t >= self.until:
            self.state, target = 'leave', self.home
            self._say('비킴', t, robot)
        if target is None:
            self.vx = self.vy = 0.0
            return
        self.waypoints, self.goal_index = [target, target], 0
        super().step(dt, t, robot, others, walls)


if __name__ == '__main__':
    mo.Person = StandPerson
    mo.main()
