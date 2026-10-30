"""Curated Tibetan Plateau boundary; downloaded for local use, never bundled."""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

PAGE='https://geodoi.ac.cn/webcn/geodoi.aspx?Id=1847'
ARCHIVE='https://geodoi.ac.cn/webcn/down.aspx?fileID=5859&size=324316'
DOI='10.3974/geodb.2021.07.10.V1'


def candidate():
    return dict(name='青藏高原（张镱锂等，2021年版完整自然地理范围）',provider='geodoi_tp2021',
                osm_type=None,osm_id='geodoi:tp2021',bbox=[67.6769,25.9916,104.6825,40.0167],
                source=PAGE,download_url=ARCHIVE,doi=DOI,
                license='GCdataPR: free research use with citation; redistribution requires publisher permission',
                warning='2021 boundary includes the southern Himalaya, Hindu Kush and Pamir across nine countries; not limited to China. Boundary version is not the DEM observation year.')


def load_boundary(api,root,selected):
    from .online import download
    root=Path(root);archive=download(ARCHIVE,root/'cache/tp2021.rar',2_000_000)
    tar=shutil.which('tar')
    if not tar:raise RuntimeError('下载的高原边界为RAR格式，需要Windows自带tar解压；未找到tar，请提供本地边界数据。')
    folder=root/'tp2021';folder.mkdir()
    # Extract exact known members to stdout; never use archive-provided paths.
    for suffix in ('shp','shx','dbf','prj','CPG'):
        name='TPboundaryPolygon.'+suffix
        child=subprocess.run([tar,'-xOf',str(archive),name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if child.returncode or not child.stdout:raise RuntimeError('青藏高原官方边界解压失败，请检查下载源。')
        (folder/name).write_bytes(child.stdout)
    source=str(folder/'TPboundaryPolygon.shp')
    desc=api.Describe(source)
    if desc.spatialReference.name=='Unknown':raise ValueError('高原原始边界坐标系未定义，已停止。')
    geometries=[row[0].projectAs(api.SpatialReference(4326)) for row in api.da.SearchCursor(source,['SHAPE@'])]
    if len(geometries)!=1:raise ValueError('高原边界数据结构发生变化，请重新验证提供者。')
    geometry=geometries[0];rings=json.loads(geometry.JSON)['rings']
    if len(rings)!=1:raise ValueError('高原边界出现多环结构，请重新验证提供者。')
    selected=dict(selected,geojson={'type':'Polygon','coordinates':rings},
                  bbox=[geometry.extent.XMin,geometry.extent.YMin,geometry.extent.XMax,geometry.extent.YMax],
                  archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    return selected
