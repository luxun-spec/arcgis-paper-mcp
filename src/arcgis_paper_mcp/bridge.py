"""ArcGIS Pro bridge: snapshot CURRENT once, process isolated file-based jobs."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from .transport import process_one, queue_dir

_thread = None
_stop_event = None


def start(queue: str | None = None):
    """Run once in Pro's Python window. Keep one bridge per private local queue."""
    global _thread, _stop_event
    import arcpy
    from .backend import Engine, dispatch
    stop()
    if queue:
        os.environ['PAPER_MCP_QUEUE'] = str(Path(queue).expanduser().resolve())
    q = queue_dir()
    q.mkdir(parents=True,exist_ok=True)
    import uuid
    # CURRENT is accessed only here on Pro's Python thread. Its COM reference
    # is never passed to the worker. Native maps are created in an isolated APRX.
    snapshot = q/f'pro-snapshot-{uuid.uuid4().hex}.aprx'
    current = arcpy.mp.ArcGISProject('CURRENT')
    current.saveACopy(str(snapshot))
    event = threading.Event()
    _stop_event = event

    def work():
        try:
            engine = Engine(arcpy.mp.ArcGISProject(str(snapshot)))
            while not event.is_set():
                try:
                    process_one(q,lambda op,params: dispatch(op,params,engine))
                except Exception as exc:
                    print(f'Paper MCP bridge: {exc}')
                event.wait(.2)
        finally:
            # Snapshot remains while the bridge may hold ArcGIS file locks.
            pass

    _thread = threading.Thread(target=work,daemon=True,name='Paper-MCP-Bridge')
    _thread.start()
    print(f'Paper MCP bridge ready: {q}')
    return {'queue':str(q),'project':current.filePath,'snapshot':str(snapshot)}


def stop():
    global _thread, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=.5)
        if _thread.is_alive():
            raise RuntimeError('A job is running. Wait for it to finish before restarting the bridge.')
    _thread = None
    _stop_event = None
