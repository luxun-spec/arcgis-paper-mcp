"""Portable configuration and page geometry, independent of ArcPy."""
from __future__ import annotations

import json
import math
from pathlib import Path

PATHS = ('boundary', 'dem', 'rivers', 'basins', 'admin', 'sites', 'world', 'country', 'project')
DEFAULTS = dict(template='study_area', title='Study area', subtitle='', source_notes='',
                dpi=300, detail_crs=3857, national_crs=3857, font='Arial',
                language='en', formats=['PNG', 'PDF'], graticule=True,
                river_order_field='', site_label_field='', padding=1.12,
                hillshade=True, demo=False, dem_unit='m')
ALLOWED = set(PATHS) | set(DEFAULTS) | {'output_dir', 'national_extent', 'globe_center', 'dem_unit'}


def frames(template: str) -> dict[str, tuple[float, float, float, float]]:
    if template == 'journal':
        return {'national': (12, 108, 69, 65), 'detail': (94, 35, 190, 138),
                'legend': (12, 35, 69, 61)}
    if template == 'study_area':
        return {'globe': (12, 121, 94, 63), 'national': (115, 121, 170, 63),
                'detail': (12, 27, 211, 81), 'legend': (232, 27, 53, 81)}
    if template == 'watershed':
        return {'detail': (12, 35, 195, 145), 'basins': (218, 119, 67, 61),
                'legend': (218, 35, 67, 75)}
    raise ValueError('template must be study_area, watershed or journal')


def _path(value: str, base: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Paths must be non-empty strings')
    p = Path(value).expanduser()
    return str((base / p).resolve() if not p.is_absolute() else p.resolve())


def _positive(value, name: str, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be a finite positive number')
    if integer and (not isinstance(value, int)):
        raise ValueError(f'{name} must be an integer')


def _output(value: str, base: Path) -> str:
    out = Path(_path(value, base))
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError(f'Output directory must be new or empty: {out}')
    return str(out)


def normalize(data: dict, base: Path) -> dict:
    if not isinstance(data, dict):
        raise ValueError('Configuration must be a JSON object')
    unknown = set(data) - ALLOWED
    if unknown:
        raise ValueError(f'Unknown configuration keys: {sorted(unknown)}')
    if not data.get('boundary') or not data.get('output_dir'):
        raise ValueError('boundary and output_dir are required')
    cfg = {**DEFAULTS, **data}
    if cfg['dem_unit'] != 'm':
        raise ValueError('dem_unit must be m; convert non-metre elevation before mapping')
    frames(cfg['template'])
    _positive(cfg['dpi'], 'dpi', integer=True)
    if not 72 <= cfg['dpi'] <= 1200:
        raise ValueError('dpi must be between 72 and 1200')
    for name in ('detail_crs', 'national_crs'):
        _positive(cfg[name], name, integer=True)
    _positive(cfg['padding'], 'padding')
    if not 1 <= cfg['padding'] <= 3:
        raise ValueError('padding must be between 1 and 3')
    for name in ('graticule', 'hillshade', 'demo'):
        if not isinstance(cfg[name], bool):
            raise ValueError(f'{name} must be boolean')
    for name in ('title', 'subtitle', 'source_notes', 'font', 'river_order_field', 'site_label_field'):
        if not isinstance(cfg[name], str):
            raise ValueError(f'{name} must be text')
    if cfg['language'] not in ('en', 'zh'):
        raise ValueError('language must be en or zh')
    if not isinstance(cfg['formats'], list) or not cfg['formats'] or any(x not in ('PNG','PDF','SVG') for x in cfg['formats']):
        raise ValueError('formats must be a nonempty list of PNG, PDF, SVG')
    for name, length in [('national_extent', 4), ('globe_center', 2)]:
        if name in cfg:
            v = cfg[name]
            if not isinstance(v, list) or len(v) != length or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in v):
                raise ValueError(f'{name} must contain {length} finite numbers')
    if 'national_extent' in cfg:
        a,b,c,d = cfg['national_extent']
        if not -180 <= a < c <= 180 or not -90 <= b < d <= 90:
            raise ValueError('national_extent must be [west,south,east,north] in longitude/latitude')
    if 'globe_center' in cfg and not (-180 <= cfg['globe_center'][0] <= 180 and -90 <= cfg['globe_center'][1] <= 90):
        raise ValueError('globe_center must be [longitude,latitude]')
    for name in PATHS:
        if cfg.get(name):
            cfg[name] = _path(cfg[name], base)
    cfg['output_dir'] = _output(cfg['output_dir'], base)
    return cfg


def load_config(path: str | Path) -> dict:
    p = Path(path).resolve()
    return normalize(json.loads(p.read_text(encoding='utf-8-sig')), p.parent)


def hydrology_config(data: dict, base: Path) -> dict:
    if not isinstance(data, dict) or set(data)-{'dem','output_dir','threshold_km2'}:
        raise ValueError('Hydrology accepts only dem, output_dir, threshold_km2')
    if not all(k in data for k in ('dem','output_dir','threshold_km2')):
        raise ValueError('dem, output_dir, threshold_km2 are required')
    _positive(data['threshold_km2'], 'threshold_km2')
    return {**data, 'dem': _path(data['dem'],base), 'output_dir': _output(data['output_dir'],base)}
