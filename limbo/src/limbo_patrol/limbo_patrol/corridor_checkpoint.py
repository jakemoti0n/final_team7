"""Progress for an operator-started real dashboard route across a host reboot."""
import hashlib
import json
import os
from pathlib import Path
import time

class Checkpoint:
    def __init__(self, directory, route, boot, map_id):
        self.path = directory / 'patrol-progress.json'
        self.boot = boot
        self.map_id = map_id
        self.route = hashlib.sha256(json.dumps(route, sort_keys=True).encode()).hexdigest()
        self.index = None
        self.resume = 0
        if self.path.exists():
            old = json.loads(self.path.read_text())
            if (old['boot'] != boot and old['map'] == map_id and old['route'] == self.route
                    and 0 <= old['next'] < len(route)):
                self.resume = old['next']

    def save(self, index):
        if index == self.index:
            return
        tmp = self.path.with_suffix('.tmp')
        with tmp.open('w') as f:
            json.dump(dict(boot=self.boot, map=self.map_id, route=self.route, next=index), f)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)
        self.index = index

def dashboard_checkpoint(route_file, route, sim, loop):
    if sim or loop or Path(route_file).resolve() != (Path.home()/'limbo/relay_prog/state/waypoints/dashboard_waypoints.yaml'):
        return None
    directory = Path.home()/'.local/state/limbo'
    if not (Path.home()/'.config/limbo/boot/corridor_pose.py').exists():
        return None
    pose = json.loads((directory/'corridor-pose.json').read_text())
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if pose.get('boot') != boot or not 0 <= time.time()-pose['time'] <= 5:
        raise RuntimeError('No recent scan-validated map pose. Wait for localization before starting patrol.')
    return Checkpoint(directory, route, boot, pose['map'])
