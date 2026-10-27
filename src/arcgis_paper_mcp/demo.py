"""Generate synthetic research layers, never presented as real observations."""
from __future__ import annotations

import json
from pathlib import Path


def create_demo(output_dir: str, project: str, world=None, country=None) -> dict:
    import arcpy as a
    import numpy as np
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError('Demo directory must be new or empty')
    if not Path(project).is_file():
        raise FileNotFoundError(project)
    root.mkdir(parents=True,exist_ok=True)
    sr = a.SpatialReference(32649)
    gdb = str(root/'synthetic.gdb')
    a.management.CreateFileGDB(str(root),'synthetic.gdb')
    x0,y0 = 280000,2450000
    width,height = 360000,195000

    def poly(coords):
        return a.Polygon(a.Array([a.Point(x0+x,y0+y) for x,y in coords]),sr)

    coords = [(15000,80000),(0,125000),(40000,155000),(70000,151000),(100000,184000),
              (139000,172000),(180000,195000),(224000,166000),(263000,174000),
              (285000,138000),(340000,145000),(360000,100000),(331000,68000),
              (294000,74000),(270000,30000),(224000,41000),(193000,10000),
              (147000,22000),(118000,0),(76000,36000),(39000,32000),(15000,80000)]
    boundary = str(root/'boundary.shp')
    a.management.CopyFeatures([poly(coords)],boundary)
    nx,ny = 720,390
    xx,yy = np.meshgrid(np.linspace(0,1,nx),np.linspace(0,1,ny))
    rng = np.random.default_rng(27)
    z = 120+2600*(.65*(1-xx)+.35*yy)**1.8
    z += 290*np.sin(xx*22+yy*10)*np.cos(yy*15) + 150*np.sin(xx*47-yy*21)
    z += rng.normal(0,12,z.shape)
    # NumPy rows begin at north, unlike the normalized yy coordinate above.
    z = np.flipud(np.maximum(z,0).astype('float32'))
    dem = str(root/'dem.tif')
    a.NumPyArrayToRaster(z,a.Point(x0,y0),width/nx,height/ny).save(dem)
    a.management.DefineProjection(dem,sr)
    a.Raster(dem).setStatistics([{'min':float(z.min()),'max':float(z.max()),
                                'mean':float(z.mean()),'standardDeviation':float(z.std()),
                                'count':int(z.size)}])
    rivers = str(Path(gdb)/'rivers')
    a.management.CreateFeatureclass(gdb,'rivers','POLYLINE',spatial_reference=sr)
    a.management.AddField(rivers,'ORDER_NO','SHORT')
    with a.da.InsertCursor(rivers,['SHAPE@','ORDER_NO']) as cursor:
        for i,(start,end,order) in enumerate([(0.05,.96,4),(.12,.55,3),(.25,.62,2),(.45,.77,2),(.58,.86,1)]):
            t = np.linspace(start,end,120)
            y = .48+.085*np.sin(t*17+i*.6)
            if i:
                y += np.linspace(.36 if i%2 else -.30,0,len(t))
            line = a.Polyline(a.Array([a.Point(x0+width*x,y0+height*value) for x,value in zip(t,y)]),sr)
            cursor.insertRow([line,order])
    basins = str(Path(gdb)/'basins')
    a.management.CreateFeatureclass(gdb,'basins','POLYGON',spatial_reference=sr)
    a.management.AddField(basins,'BASIN_ID','SHORT')
    geom = poly(coords)
    with a.da.InsertCursor(basins,['SHAPE@','BASIN_ID']) as cursor:
        for i in range(6):
            left,right = width*i/6,width*(i+1)/6
            slab = poly([(left,-1000),(right,-1000),(right,height+1000),(left,height+1000),(left,-1000)])
            cursor.insertRow([geom.intersect(slab,4),i+1])
    sites = str(Path(gdb)/'sites')
    a.management.CreateFeatureclass(gdb,'sites','POINT',spatial_reference=sr)
    a.management.AddField(sites,'SITE_ID','TEXT',field_length=16)
    with a.da.InsertCursor(sites,['SHAPE@XY','SITE_ID']) as cursor:
        for i,t in enumerate([.16,.3,.44,.58,.72,.85]):
            cursor.insertRow([(x0+width*t,y0+height*(.48+.085*np.sin(t*17))),f'S{i+1}'])
    base = dict(boundary=boundary,dem=dem,rivers=rivers,basins=basins,sites=sites,
                project=str(Path(project).resolve()),detail_crs=32649,national_crs=102012,
                title='Study area and drainage network',subtitle='Three-scale locator / shaded terrain / sampling sites',
                source_notes='Research layers: algorithmically generated synthetic data; elevation is not observed.',
                river_order_field='ORDER_NO',site_label_field='SITE_ID',demo=True,
                national_extent=[73,17,136,54],globe_center=[105,32],formats=['PNG','PDF','SVG'])
    for key,value in [('world',world),('country',country)]:
        if value:
            base[key] = str(Path(value).resolve())
    configs = []
    for template in ('study_area','watershed'):
        cfg = {**base,'template':template,'output_dir':str(root/f'map-output-{template}')}
        path = root/f'{template}.json'
        path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
        configs.append(str(path))
    (root/'SYNTHETIC_DATA_NOTICE.txt').write_text('All research layers in this directory are synthetic demonstrations, not observations or real drainage delineations. Optional world/country reference polygons retain their own provenance.',encoding='utf-8')
    return {'configs':configs,'data_dir':str(root),'synthetic':True}
