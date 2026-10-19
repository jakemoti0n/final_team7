"""Persist the configured patrol route with revision checks and atomic replacement."""
import hashlib
import math
import os
from pathlib import Path
import tempfile

import yaml


class WaypointError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class WaypointFile:
    def __init__(self, path, map_meta):
        self.path = Path(path).resolve()  # Keep installed/source symlinks intact on replace.
        self.map = map_meta

    def read(self):
        raw = self.path.read_bytes()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict) or not isinstance(data.get('waypoints'), list):
            raise WaypointError('invalid_route', 'Waypoint YAML must contain a waypoints list')
        return data, hashlib.sha256(raw).hexdigest()

    def document(self):
        data, revision = self.read()
        return {'revision': revision, 'waypoints': data['waypoints'], 'file': self.path.name,
                'applies': 'next_patrol_start'}

    def change(self, request):
        if not isinstance(request, dict) or not isinstance(request.get('revision'), str):
            raise WaypointError('invalid_payload', 'revision is required')
        data, revision = self.read()
        if request['revision'] != revision:
            raise WaypointError('revision_conflict', 'Waypoint file changed; reload and try again')
        points = data['waypoints']
        action = request.get('action')
        if action == 'add':
            value = request.get('waypoint')
            if not isinstance(value, dict) or set(value) != {'name', 'type', 'x', 'y'}:
                raise WaypointError('invalid_payload', 'New waypoint needs name, type, x and y')
            new = {**value, 'yaw': 0.0, 'wait_sec': 0}
            if new['type'] == 'pass' and points:
                points.insert(len(points) - 1, new)
            else:
                points.append(new)
        elif action in ('move', 'delete'):
            name = request.get('name')
            if not isinstance(name, str):
                raise WaypointError('invalid_payload', 'name is required')
            index = next((i for i, p in enumerate(points) if p['name'] == name), None)
            if index is None:
                raise WaypointError('not_found', 'Waypoint was not found')
            if action == 'delete':
                del points[index]
            else:
                if set(request) != {'revision', 'action', 'name', 'x', 'y'}:
                    raise WaypointError('invalid_payload', 'Move needs x and y')
                points[index] = {**points[index], 'x': request['x'], 'y': request['y']}
        elif action == 'rename':
            if set(request) != {'revision', 'action', 'name', 'new_name'} or not isinstance(request['name'], str) or not isinstance(request['new_name'], str):
                raise WaypointError('invalid_payload', 'Rename needs name and new_name')
            index = next((i for i, p in enumerate(points) if p['name'] == request['name']), None)
            if index is None:
                raise WaypointError('not_found', 'Waypoint was not found')
            points[index] = {**points[index], 'name': request['new_name'].strip()}
        elif action == 'reorder':
            if set(request) != {'revision', 'action', 'order'} or not isinstance(request['order'], list) or not all(isinstance(n, str) for n in request['order']):
                raise WaypointError('invalid_payload', 'Reorder needs a list of waypoint names')
            order = request['order']
            names = [p['name'] for p in points]
            if len(order) != len(names) or len(set(order)) != len(order) or set(order) != set(names):
                raise WaypointError('invalid_payload', 'Reorder must include each current waypoint exactly once')
            by_name = {p['name']: p for p in points}
            data['waypoints'] = points = [by_name[name] for name in order]
        else:
            raise WaypointError('invalid_payload', 'action must be add, move, delete, rename or reorder')
        self._validate(points)
        rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).encode('utf-8')
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.waypoints-', suffix='.yaml', delete=False) as output:
                temp = Path(output.name)
                output.write(rendered)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temp, self.path.stat().st_mode & 0o777)
            os.replace(temp, self.path)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
        return self.document()

    def _validate(self, points):
        if not points or not isinstance(points[-1], dict) or points[-1].get('type') != 'stop':
            raise WaypointError('invalid_route', 'The final waypoint must be a stop')
        seen = set()
        x0, y0 = self.map['origin'][:2]
        x1 = x0 + self.map['width'] * self.map['resolution']
        y1 = y0 + self.map['height'] * self.map['resolution']
        for p in points:
            if not isinstance(p, dict) or not isinstance(p.get('name'), str) or not 1 <= len(p['name'].strip()) <= 32:
                raise WaypointError('invalid_route', 'Each waypoint needs a name of 1–32 characters')
            key = p['name'].strip().casefold()
            if key in seen:
                raise WaypointError('invalid_route', 'Waypoint names must be unique')
            seen.add(key)
            if p.get('type') not in ('pass', 'stop'):
                raise WaypointError('invalid_route', 'Waypoint type must be pass or stop')
            for field in ('x', 'y', 'yaw', 'wait_sec'):
                value = p.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise WaypointError('invalid_route', f'Waypoint {field} must be finite')
            if not x0 <= p['x'] <= x1 or not y0 <= p['y'] <= y1:
                raise WaypointError('invalid_route', 'Waypoint position must be inside the map')
            if p['wait_sec'] < 0:
                raise WaypointError('invalid_route', 'wait_sec cannot be negative')
