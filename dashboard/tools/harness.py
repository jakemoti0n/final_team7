"""Local verification helpers. Subprocesses and files belong to dashboard only."""
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def get(url):
    with urllib.request.urlopen(url, timeout=1) as response:
        return json.load(response)


def wait_for(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            value = predicate()
            if value:
                return value
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(.01)
    raise AssertionError('verification deadline exceeded')


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(2)


@contextmanager
def server():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    with (ROOT / 'artifacts/server.log').open('w') as log:
        process = subprocess.Popen([str(ROOT / '.venv/bin/python'), '-m', 'uvicorn', 'server.app:app',
                                    '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, stdout=log, stderr=log)
        try:
            wait_for(lambda: get(url + '/healthz'))
            yield url
        finally:
            stop(process)
