"""Public data discovery, bounded downloads and provenance for ArcGIS jobs."""
from __future__ import annotations
import hashlib
import json
import math
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

_lock=threading.Lock()
_last_search=0.0
USER_AGENT='ArcGIS-Paper-MCP/0.2 (https://github.com/luxun-spec/arcgis-paper-mcp)'

def catalog():
    return [dict(id='osm_boundary',kind='vector',url='https://nominatim.openstreetmap.org/',
                 license='OpenStreetMap ODbL; attribution required',supports_year_filter=False,
                 limitations='Community boundaries, not authoritative legal/survey boundaries; ambiguous names require selection'),
            dict(id='terrain_tiles',kind='raster',url='https://registry.opendata.aws/terrain-tiles/',
                 license='Source-dependent; Tilezen attribution required',supports_year_filter=False,
                 limitations='Multi-source elevation mosaic, variable source resolution, not a dated 30m product'),
            dict(id='natural_earth',kind='vector',url='https://www.naturalearthdata.com/',
                 license='Public domain',supports_year_filter=False,
                 limitations='1:110m overview only; unsuitable for detailed administrative boundary analysis')]

def download(url,path,max_bytes=16_000_000):
    path=Path(path)
    if path.exists(): return path
    path.parent.mkdir(parents=True,exist_ok=True)
    request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
    with urllib.request.urlopen(request,timeout=60) as response:
        data=response.read(max_bytes+1)
    if len(data)>max_bytes: raise ValueError('Download exceeds byte budget')
    temp=path.with_suffix(path.suffix+'.partial')
    temp.write_bytes(data)
    temp.replace(path)
    return path

def search_regions(query,cache_dir):
    global _last_search
    if not isinstance(query,str) or not 1<=len(query.strip())<=200:
        raise ValueError('Supply a specific region/place name, up to 200 characters')
    cache=Path(cache_dir)/('region-'+hashlib.sha256(query.encode()).hexdigest()+'.json')
    url='https://nominatim.openstreetmap.org/search?'+urllib.parse.urlencode(dict(q=query,format='jsonv2',polygon_geojson=1,addressdetails=1,limit=5))
    with _lock:
        if not cache.exists():
            time.sleep(max(0,1.1-(time.monotonic()-_last_search)))
            try:
                download(url,cache)
            except urllib.error.URLError as exc:
                # A public country-only fallback; never substitute a country
                # polygon for a requested city or province.
                fallback='https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson'
                path=download(fallback,Path(cache_dir)/'natural-earth-countries.geojson')
                rows=[]
                for feature in json.loads(path.read_text(encoding='utf-8'))['features']:
                    props=feature['properties']
                    names=[str(props.get(k,'')).casefold() for k in ('ADMIN','NAME','NAME_EN','NAME_ZH','ISO_A3','SOVEREIGNT')]
                    if query.strip().casefold() not in names: continue
                    coords=[]
                    def visit(v):
                        if isinstance(v,list) and v and isinstance(v[0],(int,float)): coords.append(v)
                        elif isinstance(v,list):
                            for item in v: visit(item)
                    visit(feature['geometry']['coordinates'])
                    xs,ys=zip(*[(p[0],p[1]) for p in coords])
                    rows.append(dict(name=props.get('ADMIN',query),osm_type=None,osm_id='ne:'+props.get('ADM0_A3',query),
                                     bbox=[min(xs),min(ys),max(xs),max(ys)],geojson=feature['geometry'],source=fallback,
                                     license='Natural Earth public domain',warning='Nominatim unavailable; country-only 1:110m fallback, not detailed administrative data'))
                if not rows: raise RuntimeError('Place search unavailable and no exact country fallback; no boundary substituted') from exc
                return rows
            finally: _last_search=time.monotonic()
    rows=json.loads(cache.read_text(encoding='utf-8'))
    return [dict(name=r['display_name'],osm_type=r.get('osm_type'),osm_id=r.get('osm_id'),
                 bbox=[float(r['boundingbox'][2]),float(r['boundingbox'][0]),float(r['boundingbox'][3]),float(r['boundingbox'][1])],
                 geojson=r.get('geojson'),source=url,license='© OpenStreetMap contributors, ODbL') for r in rows]

def choose_region(rows):
    polygons=[r for r in rows if r.get('geojson',{}).get('type') in ('Polygon','MultiPolygon')]
    if not polygons: raise ValueError('No polygon boundary found; specify a more precise administrative region or supply a boundary file')
    if len(polygons)!=1: raise ValueError('Multiple polygon boundaries found; select an osm_id from search_regions first')
    return polygons[0]

def tile_plan(bbox,zoom=9,max_tiles=64):
    if not isinstance(zoom,int) or isinstance(zoom,bool) or not 5<=zoom<=12:
        raise ValueError('zoom must be an integer from 5 to 12')
    w,s,e,n=bbox
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in bbox) or not (-180<=w<e<=180 and -85<s<n<85):
        raise ValueError('Invalid WGS84 bbox, antimeridian regions require separate jobs')
    size=2**zoom
    def xy(lon,lat): return min(size-1,int((lon+180)/360*size)),min(size-1,int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*size))
    x0,y1=xy(w,s); x1,y0=xy(e,n)
    count=(x1-x0+1)*(y1-y0+1)
    if count>max_tiles: raise ValueError(f'{count} tiles required, maximum {max_tiles}; reduce zoom or region explicitly')
    return dict(zoom=zoom,tiles=[(x,y) for y in range(y0,y1+1) for x in range(x0,x1+1)],
                x0=x0,y0=y0,x1=x1,y1=y1,pixel_size_mercator_m=40075016.68557849/(size*256))

def prepare_online(api,region,workspace,zoom=9,osm_id=None):
    """Run in ArcGIS Python. No provider tokens, arbitrary URLs or synthetic data."""
    import numpy as np
    from PIL import Image
    import zipfile
    root=Path(workspace).resolve()
    if root.exists() and any(root.iterdir()): raise FileExistsError('Online workspace must be new or empty')
    root.mkdir(parents=True,exist_ok=True)
    rows=search_regions(region,root/'cache')
    if osm_id is not None: rows=[r for r in rows if str(r['osm_id'])==str(osm_id)]
    selected=choose_region(rows)
    plan=tile_plan(selected['bbox'],zoom)
    geo=root/'boundary.geojson'
    geo.write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'name':region},'geometry':selected['geojson']}]}),encoding='utf-8')
    boundary=root/'boundary.shp'
    api.conversion.JSONToFeatures(str(geo),str(boundary),'POLYGON')
    if api.Describe(str(boundary)).spatialReference.name=='Unknown':
        # GeoJSON positions are defined as WGS84 longitude/latitude.
        api.management.DefineProjection(str(boundary),api.SpatialReference(4326))
    values=np.zeros(((plan['y1']-plan['y0']+1)*256,(plan['x1']-plan['x0']+1)*256),dtype='float32')
    tiles=[]
    for x,y in plan['tiles']:
        url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png'
        path=download(url,root/'cache'/f'{zoom}-{x}-{y}.png',1_000_000)
        rgb=np.asarray(Image.open(path).convert('RGB'),dtype='float32')
        if rgb.shape!=(256,256,3): raise ValueError('Unexpected terrain tile dimensions')
        values[(y-plan['y0'])*256:(y-plan['y0']+1)*256,(x-plan['x0'])*256:(x-plan['x0']+1)*256]=rgb[:,:,0]*256+rgb[:,:,1]+rgb[:,:,2]/256-32768
        tiles.append(dict(url=url,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    dem=root/'elevation_source.tif'
    cell=plan['pixel_size_mercator_m']; half=20037508.342789244
    api.NumPyArrayToRaster(values,api.Point(-half+plan['x0']*256*cell,half-(plan['y1']+1)*256*cell),cell,cell).save(str(dem))
    api.management.DefineProjection(str(dem),api.SpatialReference(3857))
    api.Raster(str(dem)).setStatistics([dict(min=float(values.min()),max=float(values.max()),mean=float(values.mean()),standardDeviation=float(values.std()))])
    archive=download('https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_countries.zip',root/'cache/world.zip')
    world_dir=root/'world';world_dir.mkdir()
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            destination=(world_dir/item.filename).resolve()
            if not destination.is_relative_to(world_dir.resolve()): raise ValueError('Unsafe archive entry')
        z.extractall(world_dir)
    attribution=download('https://raw.githubusercontent.com/tilezen/joerd/master/docs/attribution.md',root/'TERRAIN_ATTRIBUTION.md')
    provenance=dict(region=selected,terrain=plan,tiles=tiles,providers=catalog(),
                    retrieved_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                    warning='Elevation is a multi-source mosaic, not year-specific; boundaries are community data. No rivers, land cover or sampling points have been invented.')
    (root/'data_sources.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    w,s,e,n=selected['bbox'];lon=(w+e)/2;lat=(s+n)/2
    zone=min(60,max(1,int((lon+180)/6)+1))
    return dict(boundary=str(boundary),dem=str(dem),world=str(world_dir/'ne_110m_admin_0_countries.shp'),
                detail_crs=(32600 if lat>=0 else 32700)+zone,provenance=provenance)
