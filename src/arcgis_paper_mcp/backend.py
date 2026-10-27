"""Allowlisted ArcPy operations. Importable/testable without an ArcGIS license."""
from __future__ import annotations

import contextlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import PATHS, frames, hydrology_config, normalize
from .transport import OPERATIONS, atomic_json


def describe(api, path: str) -> dict:
    if not api.Exists(path):
        raise FileNotFoundError(f'Dataset not found: {path}')
    d = api.Describe(path)
    sr = getattr(d, 'spatialReference', None)
    if sr is None or sr.name in ('Unknown', '') or sr.type == 'Unknown':
        raise ValueError(f'Dataset has no known coordinate system: {path}')
    e = d.extent
    result = dict(path=path, data_type=d.dataType, crs=sr.name, wkid=sr.factoryCode,
                  crs_type=sr.type, extent=[e.XMin,e.YMin,e.XMax,e.YMax])
    if hasattr(d,'shapeType'):
        result['geometry_type'] = d.shapeType
        result['fields'] = [f.name for f in api.ListFields(path)]
        result['feature_count'] = int(api.management.GetCount(path)[0])
    if hasattr(d,'meanCellWidth'):
        result['cell_size'] = [d.meanCellWidth,d.meanCellHeight]
    return result


def metric_cell_area(d) -> float:
    sr = d.spatialReference
    if sr.type != 'Projected' or sr.linearUnitName.lower() not in ('meter','metre','meters','metres'):
        raise ValueError('Hydrology DEM must use a projected coordinate system in metres; reproject explicitly first')
    area = abs(d.meanCellWidth*d.meanCellHeight)
    if not math.isfinite(area) or area <= 0:
        raise ValueError('Invalid DEM cell dimensions')
    return area


def threshold_cells(d, threshold_km2: float) -> int:
    return max(1, math.ceil(threshold_km2*1_000_000/metric_cell_area(d)))


def _rect(api, x,y,w,h):
    return api.Polygon(api.Array([api.Point(x,y),api.Point(x+w,y),api.Point(x+w,y+h),api.Point(x,y+h),api.Point(x,y)]))


def _style(proj, category, name=''):
    styles = proj.listStyleItems('ArcGIS 2D', category, name) if name else proj.listStyleItems('ArcGIS 2D',category)
    return styles[0] if styles else None


def _vector(m, path, name, *, color, width=0.6, fill=None, geometry_type='Polygon'):
    layer = m.addDataFromPath(path)
    layer.name = name
    sym = layer.symbology
    if hasattr(sym,'renderer'):
        sym.updateRenderer('SimpleRenderer')
        symbol = sym.renderer.symbol
        if geometry_type == 'Polygon':
            symbol.color = {'RGB': fill or [255,255,255,0]}
            symbol.outlineColor = {'RGB':color}
            symbol.outlineWidth = width
        else:
            symbol.color = {'RGB':color}
            if geometry_type in ('Point','Multipoint'):
                symbol.size = 4.5
                symbol.outlineColor = {'RGB':[255,255,255,100]}
                symbol.outlineWidth = 0.5
            else:
                symbol.size = width
        layer.symbology = sym
    return layer


def _field(api, path, name):
    actual = {f.name.casefold(): f.name for f in api.ListFields(path)}
    if name.casefold() not in actual:
        raise ValueError(f'Field {name!r} not found in {path}')
    return actual[name.casefold()]


def _unique(layer, field, palette, widths=None):
    sym = layer.symbology
    sym.updateRenderer('UniqueValueRenderer')
    sym.renderer.fields = [field]
    for i,item in enumerate(item for group in sym.renderer.groups for item in group.items):
        item.symbol.color = {'RGB':palette[i % len(palette)]}
        if widths:
            item.symbol.size = widths[min(i,len(widths)-1)]
        else:
            item.symbol.outlineColor = {'RGB':[255,255,255,100]}
            item.symbol.outlineWidth = 0.4
    layer.symbology = sym


def _raster_colors(layer):
    sym = layer.symbology
    sym.updateColorizer('RasterClassifyColorizer')
    sym.colorizer.breakCount = 6
    colors = [[24,104,75,100],[75,151,91,100],[151,191,114,100],
              [221,226,158,100],[239,225,182,100],[193,169,140,100]]
    for brk,color in zip(sym.colorizer.classBreaks,colors):
        brk.color = {'RGB':color}
    layer.symbology = sym


def _hillshade(api, source, out, warnings):
    """Display-only relief: bounded NumPy computation, no analyst extension."""
    import numpy as np
    d = api.Describe(source)
    span = max(d.extent.width,d.extent.height)
    cell = max(abs(d.meanCellWidth),abs(d.meanCellHeight),span/1800)
    reduced = str(out/'relief_source.tif')
    api.management.Resample(source,reduced,cell,'BILINEAR')
    raster = api.Raster(reduced)
    data = api.RasterToNumPyArray(raster,nodata_to_value=-999999).astype('float64')
    invalid = data == -999999
    if invalid.all() or min(data.shape) < 2:
        raise ValueError('DEM has too few valid pixels for relief')
    data[invalid] = np.median(data[~invalid])
    dx,dy = float(raster.meanCellWidth),float(raster.meanCellHeight)
    if d.spatialReference.type == 'Geographic':
        lat = (d.extent.YMin+d.extent.YMax)/2
        dx *= 111320*max(0.05,math.cos(math.radians(lat)))
        dy *= 111320
        warnings.append('Relief uses approximate degree-to-metre spacing at DEM central latitude; display only')
    else:
        factor = getattr(d.spatialReference,'metersPerUnit',1)
        dx *= factor
        dy *= factor
    gy,gx = np.gradient(data,dy,dx)
    # Rows run north-to-south. Illumination from NW at 45 degree altitude.
    nx,ny,nz = -gx,gy,np.ones_like(gx)
    shade = (nx*(-0.5)+ny*0.5+nz*(2**-0.5))/np.sqrt(nx*nx+ny*ny+1)
    shade = np.clip(70+185*np.maximum(shade,0),0,255).astype('uint8')
    shade[invalid] = 0
    result = str(out/'hillshade.tif')
    api.NumPyArrayToRaster(shade,api.Point(raster.extent.XMin,raster.extent.YMin),
                           raster.meanCellWidth,raster.meanCellHeight,0).save(result)
    api.management.DefineProjection(result,d.spatialReference)
    return result


def _orthographic(api, lon,lat):
    sr = api.SpatialReference()
    sr.loadFromString('PROJCS["Paper_Orthographic",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
                      'SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],'
                      'UNIT["Degree",0.0174532925199433]],PROJECTION["Orthographic"],'
                      f'PARAMETER["False_Easting",0],PARAMETER["False_Northing",0],'
                      f'PARAMETER["Central_Meridian",{lon}],PARAMETER["Latitude_Of_Origin",{lat}],UNIT["Meter",1]]')
    return sr


class Engine:
    def __init__(self, project=None):
        import arcpy
        self.api = arcpy
        self.project = project

    def ping(self, **params):
        a = self.api
        info = a.GetInstallInfo()
        return dict(version=info.get('Version'),product=a.ProductInfo(),
                    spatial_analyst=a.CheckExtension('Spatial'),
                    project=getattr(self.project,'filePath',None),
                    maps=[m.name for m in self.project.listMaps()] if self.project else [])

    def inspect_data(self, path):
        return describe(self.api,str(Path(path).expanduser().resolve()))

    def render_map(self, config):
        cfg = normalize(config,Path.cwd())
        a = self.api
        warnings = []
        sources = {name:describe(a,cfg[name]) for name in PATHS if cfg.get(name) and name != 'project'}
        if sources['boundary'].get('geometry_type') != 'Polygon':
            raise ValueError('boundary must be a polygon dataset')
        for key in ('world','country','basins','admin'):
            if key in sources and sources[key].get('geometry_type') != 'Polygon':
                raise ValueError(f'{key} must contain polygons')
        for key in ('rivers',):
            if key in sources and sources[key].get('geometry_type') != 'Polyline':
                raise ValueError(f'{key} must contain polylines')
        if 'sites' in sources and sources['sites'].get('geometry_type') not in ('Point','Multipoint'):
            raise ValueError('sites must contain points')
        if 'dem' in sources and 'cell_size' not in sources['dem']:
            raise ValueError('dem must be a raster dataset')
        if cfg['river_order_field']:
            if not cfg.get('rivers'):
                raise ValueError('river_order_field requires rivers')
            _field(a,cfg['rivers'],cfg['river_order_field'])
        if cfg['site_label_field']:
            if not cfg.get('sites'):
                raise ValueError('site_label_field requires sites')
            _field(a,cfg['sites'],cfg['site_label_field'])
        detail_sr = a.SpatialReference(cfg['detail_crs'])
        national_sr = a.SpatialReference(cfg['national_crs'])
        if detail_sr.type != 'Projected':
            raise ValueError('detail_crs must be a projected CRS for map scale')
        if national_sr.name == 'Unknown':
            raise ValueError('Invalid national_crs')
        seed = self.project
        if cfg.get('project'):
            if not Path(cfg['project']).is_file():
                raise FileNotFoundError(cfg['project'])
            seed = a.mp.ArcGISProject(cfg['project'])
        if seed is None:
            raise ValueError('Headless rendering requires config.project pointing to an existing APRX; or start the Pro bridge')
        out = Path(cfg['output_dir'])
        out.mkdir(parents=True,exist_ok=True)
        target = out/'study_area.aprx'
        seed.saveACopy(str(target))
        proj = a.mp.ArcGISProject(str(target))
        # Only the new copy is cleared, never the source or CURRENT project.
        for item in proj.listLayouts()+proj.listMaps():
            proj.deleteItem(item)
        try:
            proj.updateStyles(['ArcGIS 2D'])
        except Exception as exc:
            warnings.append(f'Could not load ArcGIS 2D styles: {exc}')
        layout = proj.createLayout(297,210,'MILLIMETER','Paper - '+cfg['template'])
        zh = cfg['language'] == 'zh'
        label = lambda en,cn: cn if zh else en

        def text(x,y,value,size=8,name=None):
            # Escape markup so source notes and titles cannot become broken text XML.
            import html
            return proj.createTextElement(layout,a.Point(x,y),'POINT',html.escape(value),size,
                                          cfg['font'],'Regular',name=name or value[:24])

        def newmap(name,sr):
            m = proj.createMap(name,'MAP')
            for lyr in m.listLayers():
                m.removeLayer(lyr)
            m.spatialReference = sr
            return m

        colors = [[175,210,220,100],[218,205,171,100],[182,204,164,100],
                  [200,183,210,100],[230,195,178,100],[202,216,173,100],
                  [167,198,214,100],[222,204,224,100]]
        detail = newmap('Study area',detail_sr)
        if cfg.get('dem'):
            clip = str(out/'elevation.tif')
            with a.EnvManager(overwriteOutput=False):
                a.management.Clip(cfg['dem'],'#',clip,cfg['boundary'],'#','ClippingGeometry','NO_MAINTAIN_EXTENT')
            a.management.CalculateStatistics(clip)
            if cfg['hillshade']:
                if cfg.get('dem_unit','m') != 'm':
                    raise ValueError('Relief currently requires DEM elevation in metres (dem_unit=m)')
                relief = detail.addDataFromPath(_hillshade(a,clip,out,warnings))
                relief.name = label('Shaded relief','地形阴影')
            dem = detail.addDataFromPath(clip)
            dem.name = label('Elevation (m)','高程（m）')
            _raster_colors(dem)
            dem.transparency = 23 if cfg['hillshade'] else 0
        else:
            warnings.append('No DEM supplied: terrain and hillshade omitted')
        if cfg.get('admin'):
            _vector(detail,cfg['admin'],label('Administrative boundaries','行政区界'),color=[120,124,122,100],width=.35)
        if cfg.get('rivers'):
            rivers = _vector(detail,cfg['rivers'],label('Rivers','河流'),color=[23,145,181,100],width=.85,geometry_type='Polyline')
            if cfg['river_order_field']:
                _unique(rivers,cfg['river_order_field'],[[172,209,218,100],[100,173,192,100],[42,129,163,100],[18,75,113,100]], [.3,.55,.9,1.25,1.6])
        boundary = _vector(detail,cfg['boundary'],label('Study area','研究区边界'),color=[35,50,45,100],width=1)
        if cfg.get('sites'):
            sites = _vector(detail,cfg['sites'],label('Sampling sites','采样点'),color=[183,61,43,100],geometry_type='Point')
            if cfg['site_label_field']:
                lc = sites.listLabelClasses()[0]
                lc.expression = '$feature.'+cfg['site_label_field']
                lc.visible = True
                sites.showLabels = True

        geometry = a.Describe(cfg['boundary']).extent.polygon
        geo = geometry.projectAs(a.SpatialReference(4326)).extent
        lon,lat = cfg.get('globe_center',[(geo.XMin+geo.XMax)/2,(geo.YMin+geo.YMax)/2])
        maps = {'detail':detail}
        bounds = {'detail':boundary}
        if cfg['template'] == 'study_area':
            globe = newmap('Global locator',_orthographic(a,lon,lat))
            national = newmap('National locator',national_sr)
            for m in (globe,national):
                if cfg.get('world'):
                    _vector(m,cfg['world'],label('Land','陆地'),color=[130,151,149,100],width=.2,fill=[226,231,213,100])
                if cfg.get('country'):
                    country_layer = _vector(m,cfg['country'],label('Country','国家位置'),color=[48,63,58,100],width=.7,fill=[239,235,205,100])
                    if m == national:
                        bounds['national'] = country_layer
                bounds['globe' if m == globe else 'locator_area'] = _vector(m,cfg['boundary'],label('Study area','研究区'),color=[178,70,38,100],width=.7,fill=[233,166,82,100])
            maps.update(globe=globe,national=national)
            if not cfg.get('world'):
                warnings.append('No world polygons supplied: globe locator displays study boundary only')
        else:
            basin_map = newmap('Basin subdivisions',detail_sr)
            bounds['basins'] = _vector(basin_map,cfg['boundary'],label('Study area','研究区'),color=[70,85,85,100],width=.5)
            if cfg.get('basins'):
                basins = _vector(basin_map,cfg['basins'],label('Basins','流域分区'),color=[255,255,255,100],fill=colors[0])
                fields = a.ListFields(cfg['basins'])
                field = next((f.name for f in fields if f.name.lower() in ('gridcode','basin_id','value')), None)
                field = field or next(f.name for f in fields if f.type == 'OID')
                _unique(basins,field,colors)
            else:
                warnings.append('No basins supplied: subdivision inset contains only study boundary')
            maps['basins'] = basin_map

        rects = frames(cfg['template'])
        elements = {}
        for key,m in maps.items():
            x,y,w,h = rects[key]
            frame = layout.createMapFrame(_rect(a,x,y,w,h),m,key)
            frame.camera.heading = 0
            if key == 'globe':
                frame.camera.setExtent(a.Extent(-6_500_000,-6_500_000,6_500_000,6_500_000))
                try:
                    cim = frame.getDefinition('V3')
                    cim.graphicFrame.backgroundSymbol.symbol.symbolLayers[0].color.values = [207,228,235,100]
                    frame.setDefinition(cim)
                except Exception as exc:
                    warnings.append(f'Globe background style unavailable: {exc}')
            elif key == 'national' and cfg.get('national_extent'):
                e = a.Extent(*cfg['national_extent'],spatial_reference=a.SpatialReference(4326)).polygon.projectAs(m.spatialReference).extent
                frame.camera.setExtent(e)
            else:
                lyr = bounds.get(key) or bounds.get('locator_area')
                frame.camera.setExtent(frame.getLayerExtent(lyr,False,True))
                frame.camera.scale *= cfg['padding']
            if cfg['graticule'] and key != 'globe':
                try:
                    grids = proj.listStyleItems('ArcGIS 2D','GRID','*Graticule*')
                    if not grids:
                        raise RuntimeError('No graticule style in ArcGIS 2D')
                    frame.addGrid(grids[0])
                except Exception as exc:
                    warnings.append(f'{key}: graticule unavailable: {exc}')
            elements[key] = frame
            captions = {'globe':label('(a) Global location','(a) 全球位置'),
                        'national':label('(b) Regional context','(b) 区域位置'),
                        'detail':label('(c) Terrain and sampling network','(c) 地形与采样分布') if cfg['template']=='study_area' else label('(a) River network and terrain','(a) 分级水系与地形'),
                        'basins':label('(b) Basin subdivisions','(b) 流域分区')}
            text(x,y+h+2.3,captions[key],9)

        main = elements['detail']
        x,y,w,h = rects['detail']
        for category,pos,name in [('NORTH_ARROW',(x+w-10,y+h-16),'North arrow'),
                                  ('SCALE_BAR',(x+5,y+4),'Scale bar')]:
            try:
                style = _style(proj,category)
                if style is None:
                    raise RuntimeError(f'Missing {category} style')
                elem = layout.createMapSurroundElement(a.Point(*pos),category,main,style,name)
                if category == 'NORTH_ARROW':
                    elem.elementHeight = 10
                else:
                    elem.elementWidth = 42
                    cim = elem.getDefinition('V3')
                    cim.units = 'Kilometers'
                    cim.unitLabel = 'km'
                    elem.setDefinition(cim)
            except Exception as exc:
                warnings.append(f'{name} unavailable: {exc}')
        lx,ly,lw,lh = rects['legend']
        try:
            legend = layout.createMapSurroundElement(_rect(a,lx,ly+8,lw,lh-8),'LEGEND',main,_style(proj,'LEGEND'),'Legend')
            legend.title = label('Legend','图例')
            legend.syncNewLayer = False
            legend.fittingStrategy = 'AdjustFontSize'
            for item in list(legend.items):
                if item.name == label('Shaded relief','地形阴影'):
                    legend.removeItem(item)
                else:
                    item.showHeading = False
                    item.showLayerName = True
                    item.showLabels = True
            # Keep a native editable legend within the reserved column.
            legend.elementWidth = lw
            legend.elementHeight = lh-8
        except Exception as exc:
            warnings.append(f'Legend unavailable: {exc}')
        text(12,200,cfg['title'],16,'Figure title')
        if cfg['subtitle']:
            text(12,194,cfg['subtitle'],7.5,'Subtitle')
        text(12,17,label('Projection: ','投影：')+detail_sr.name,6.5,'Projection')
        if cfg['source_notes']:
            text(12,11,cfg['source_notes'],6.5,'Sources')
        if cfg['demo']:
            text(12,5,label('SYNTHETIC DEMONSTRATION — not research evidence','合成数据演示 — 不可作为科研证据'),7,'Synthetic data notice')
        if cfg['detail_crs'] == 3857:
            warnings.append('Web Mercator used: choose a suitable local projected CRS for publication and metric interpretation')
        proj.save()
        exported = []
        for fmt in dict.fromkeys(cfg['formats']):
            file = out/f"{cfg['template']}.{fmt.lower()}"
            getattr(layout,'exportTo'+fmt)(str(file),resolution=cfg['dpi'])
            if not file.is_file() or file.stat().st_size == 0:
                raise RuntimeError(f'Export did not produce a file: {file}')
            exported.append(str(file))
        manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(), arcgis_version=a.GetInstallInfo()['Version'],
                        template=cfg['template'], config=cfg, sources=sources,
                        project=str(target), exports=exported,warnings=warnings,
                        layout=layout.name, maps=[m.name for m in maps.values()],
                        synthetic=cfg['demo'])
        atomic_json(out/'manifest.json',manifest)
        return manifest

    def derive_hydrology(self, config):
        cfg = hydrology_config(config,Path.cwd())
        a = self.api
        source = describe(a,cfg['dem'])
        d = a.Describe(cfg['dem'])
        cells = threshold_cells(d,cfg['threshold_km2'])
        if a.CheckExtension('Spatial') != 'Available':
            raise RuntimeError('Spatial Analyst license is required for hydrology')
        out = Path(cfg['output_dir'])
        out.mkdir(parents=True,exist_ok=True)
        a.CheckOutExtension('Spatial')
        try:
            with a.EnvManager(overwriteOutput=False,snapRaster=cfg['dem'],cellSize=cfg['dem'],
                              extent=cfg['dem'],outputCoordinateSystem=d.spatialReference):
                filled = a.sa.Fill(cfg['dem'])
                filled.save(str(out/'filled.tif'))
                flow = a.sa.FlowDirection(filled,'NORMAL',None,'D8')
                flow.save(str(out/'flow_direction.tif'))
                accum = a.sa.FlowAccumulation(flow,None,'FLOAT','D8')
                accum.save(str(out/'flow_accumulation.tif'))
                streams = a.sa.Con(accum >= cells,1)
                streams.save(str(out/'streams.tif'))
                order = a.sa.StreamOrder(streams,flow,'STRAHLER')
                order.save(str(out/'stream_order.tif'))
                river = str(out/'rivers.shp')
                a.sa.StreamToFeature(order,flow,river,'SIMPLIFY')
                basin = a.sa.Basin(flow)
                basin.save(str(out/'basins.tif'))
                polygons = str(out/'basins.shp')
                a.conversion.RasterToPolygon(basin,polygons,'SIMPLIFY','VALUE')
            result = dict(method='Fill → D8 → FlowAccumulation → Strahler; Basin for DEM-edge drainage basins',
                          config=cfg,source=source,threshold_cells=cells,
                          cell_area_m2=metric_cell_area(d),rivers=river,basins=polygons,
                          river_order_field='grid_code',
                          note='Basin partitions edge-draining basins, not pour-point subcatchments. Clip results to your study area as needed.')
            atomic_json(out/'hydrology_manifest.json',result)
            return result
        finally:
            a.CheckInExtension('Spatial')


def dispatch(operation: str, params: dict, engine=None):
    if operation not in OPERATIONS:
        raise ValueError('Operation is not allowed')
    engine = engine or Engine()
    return getattr(engine,operation)(**params)


def main():
    request,response = map(Path,sys.argv[1:3])
    try:
        import time
        job = json.loads(request.read_text(encoding='utf-8'))
        if job['deadline'] < time.time():
            raise TimeoutError('Headless request expired')
        result = {'ok':True,'result':dispatch(job['operation'],job['params'])}
    except Exception as exc:
        result = {'ok':False,'error':f'{type(exc).__name__}: {exc}'}
    atomic_json(response,result)


if __name__ == '__main__':
    main()
