"""Local atomic file queue. No sockets and no arbitrary Python execution."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

OPERATIONS = frozenset({'ping', 'inspect_data', 'render_map', 'derive_hydrology'})


def atomic_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def process_one(queue: Path, dispatch) -> bool:
    """Called by the serialized file-project worker; one bridge per queue."""
    jobs = sorted(queue.glob('*.request.json'))
    if not jobs:
        return False
    job = jobs[0]
    identifier = job.name.removesuffix('.request.json')
    running = queue / f'{identifier}.running.json'
    try:
        job.rename(running)
    except FileNotFoundError:
        return False
    try:
        request = json.loads(running.read_text(encoding='utf-8'))
        if request.get('id') != identifier or not identifier.isalnum():
            raise ValueError('Invalid request id')
        if request['operation'] not in OPERATIONS:
            raise ValueError('Operation is not allowed')
        if request['deadline'] < time.time():
            raise TimeoutError('Request expired before execution')
        if not isinstance(request.get('params'),dict):
            raise ValueError('params must be an object')
        reply = {'ok': True, 'result': dispatch(request['operation'], request['params'])}
    except Exception as exc:
        reply = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    atomic_json(queue/f'{identifier}.response.json', reply)
    running.unlink(missing_ok=True)
    return True


def queue_dir() -> Path:
    return Path(os.environ.get('PAPER_MCP_QUEUE', str(Path.home()/'.arcgis-paper-mcp'/'queue'))).expanduser().resolve()


def call(operation: str, params: dict, timeout: float | None = None) -> dict:
    if operation not in OPERATIONS:
        raise ValueError('Operation is not allowed')
    timeout = timeout or float(os.environ.get('PAPER_MCP_TIMEOUT','600'))
    if not 0 < timeout <= 86400:
        raise ValueError('Timeout must be in (0, 86400] seconds')
    q = queue_dir()
    q.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    response = q/f'{identifier}.response.json'
    request = q/f'{identifier}.request.json'
    worker = None
    python = os.environ.get('PAPER_MCP_ARCGIS_PYTHON')
    if python:
        # A dedicated worker for this request, with project file chosen by the user.
        request = q/f'{identifier}.headless.json'
    atomic_json(request, {'id':identifier, 'deadline':time.time()+timeout,'operation':operation,'params':params})
    try:
        if python:
            worker = subprocess.Popen([python, '-m', 'arcgis_paper_mcp.backend', str(request), str(response)],
                                      stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr)
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            if response.exists():
                reply = json.loads(response.read_text(encoding='utf-8'))
                if not reply.get('ok'):
                    raise RuntimeError(reply.get('error','ArcGIS job failed'))
                return reply['result']
            if worker is not None and worker.poll() is not None:
                raise RuntimeError(f'ArcGIS Python exited ({worker.returncode}) without a response; check license/environment')
            time.sleep(0.15)
        raise TimeoutError('ArcGIS response timeout. Queued job cancelled if unclaimed; a running job may still finish. Check output directory before retrying.')
    finally:
        request.unlink(missing_ok=True)
        response.unlink(missing_ok=True)
        # Do not terminate a running ArcPy export; it could corrupt an APRX/GDB.
