"""MCP stdio tools; no ArcPy dependency in the client-facing environment."""
from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import frames, hydrology_config, load_config
from .transport import call

mcp = FastMCP('ArcGIS Paper Maps', instructions='Create editable scientific maps. Inspect datasets and validate configuration before rendering. Never invent source boundaries or research observations. Use new output folders; report manifest warnings.')

@mcp.tool()
def search_online_regions(query: str, cache_dir: str) -> list:
    """Search public OpenStreetMap region boundaries. Supply a place name extracted from the user's natural-language request. Return candidates, IDs, bbox, polygon and source; select ambiguous places explicitly."""
    from .online import search_regions
    # Keep full geometry in the local cache, not in the model's context window.
    return [{k:v for k,v in row.items() if k!='geojson'} for row in search_regions(query,cache_dir)]

@mcp.tool()
def list_online_data_sources() -> list:
    """List implemented online raster/vector providers, licensing, temporal and resolution limitations. This is a provider catalog, not arbitrary web search."""
    from .online import catalog
    return catalog()

@mcp.tool()
async def create_online_research_map(region: str, output_dir: str, project_path: str | None = None,
                                     zoom: int = 9, osm_id: str | None = None, request: str = '') -> dict:
    """Find and download real polygon boundary, elevation tiles and locator vectors; process and map them in ArcGIS Pro. Host extracts region and preserves original request. New output directory required. No dated imagery/landcover download yet; compare returned coverage to user's requirements. Headless mode requires project_path. Tile budget 64; ambiguous regions require selected osm_id."""
    return await asyncio.to_thread(call,'create_online_map',dict(region=region,output_dir=output_dir,
                                   project_path=project_path,zoom=zoom,osm_id=osm_id,request=request))


@mcp.tool()
def list_templates() -> dict:
    """List the two native ArcGIS layout templates and their data requirements."""
    return {'journal':{'description':'Compact journal layout: small regional locator, dominant terrain map, separate legend',
                       'required':['boundary','output_dir'],'frames_mm':frames('journal')},
            'study_area':{'description':'Global locator + national locator + detailed terrain map',
                          'required':['boundary','output_dir'],'recommended':['world','country','dem','rivers','sites'],
                          'frames_mm':frames('study_area')},
            'watershed':{'description':'River network and terrain + basin subdivisions inset',
                         'required':['boundary','output_dir'],'recommended':['dem','rivers','basins'],
                         'frames_mm':frames('watershed')}}


@mcp.tool()
def validate_map_config(config_path: str) -> dict:
    """Validate and normalize a local JSON configuration without requiring ArcGIS. Does not inspect dataset content."""
    return {'valid':True,'config':load_config(config_path)}


@mcp.tool()
async def ping_arcgis() -> dict:
    """Check ArcGIS version, license and bridge connectivity. Requires a running bridge or configured headless Python."""
    return await asyncio.to_thread(call,'ping',{},120)


@mcp.tool()
async def inspect_dataset(path: str) -> dict:
    """Inspect actual CRS, geometry, extent, fields and raster cell size in ArcGIS."""
    return await asyncio.to_thread(call,'inspect_data',{'path':str(Path(path).expanduser().resolve())},120)


@mcp.tool()
async def create_paper_map(config_path: str) -> dict:
    """Build native editable maps/layout, save a new APRX and export PNG/PDF/SVG. Reads JSON; output folder must be empty. Returns provenance manifest and warnings."""
    cfg = load_config(config_path)
    return await asyncio.to_thread(call,'render_map',{'config':cfg})


@mcp.tool()
async def derive_watershed(dem_path: str, output_dir: str, threshold_km2: float) -> dict:
    """Derive D8 drainage, Strahler river order and edge-draining basin partitions. Requires Spatial Analyst and DEM projected in metres. threshold_km2 is upstream contributing area, not a pixel count. DEM must cover full upstream catchments."""
    cfg = hydrology_config({'dem':dem_path,'output_dir':output_dir,'threshold_km2':threshold_km2},Path.cwd())
    return await asyncio.to_thread(call,'derive_hydrology',{'config':cfg})


@mcp.prompt()
def paper_map_workflow(research_area: str) -> str:
    return (f'为 {research_area} 制作论文区域概况图。先列出模板并确认用户提供的边界、DEM、河流和采样点；'
            '禁止把合成数据当实测数据。检查 ArcGIS 连接与数据 CRS，读取用户的 JSON 配置并校验。'
            '采用三级定位、地形设色和清晰图例，保存到新目录；完成后逐项报告 APRX、图片、数据来源和 warnings。')


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
