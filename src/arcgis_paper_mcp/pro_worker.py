"""Restricted worker for the native Pro pane. Request arrives via stdin, never a key file."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .assistant_support import request_plan, requirement_gaps, validate_plan

PROVINCES=('北京市 天津市 河北省 山西省 内蒙古自治区 辽宁省 吉林省 黑龙江省 上海市 江苏省 浙江省 '
           '安徽省 福建省 江西省 山东省 河南省 湖北省 湖南省 广东省 广西壮族自治区 海南省 重庆市 '
           '四川省 贵州省 云南省 西藏自治区 陕西省 甘肃省 青海省 宁夏回族自治区 新疆维吾尔自治区 '
           '香港 澳门 台湾省').split()


def rule_plan(request,region_hint='',defaults=None):
    """Explicit limited place matching, not a replacement for model comprehension."""
    if not isinstance(request,str) or not 1<=len(request.strip())<=8000:
        raise ValueError('请输入1到8000字的制图需求。')
    region=region_hint.strip()
    if not region:
        hits=[p for p in PROVINCES if p in request or p.removesuffix('省').removesuffix('市') in request]
        if '尼泊尔' in request or re.search(r'\bnepal\b',request,re.I):hits.append('Nepal')
        if '青藏高原' in request or re.search(r'\btibetan plateau\b',request,re.I):hits.append('青藏高原')
        if len(set(hits))!=1:
            raise ValueError('规则识别未找到唯一地区。请在“地区”栏明确填写地名，或配置模型以理解复杂需求。')
        region=hits[0]
    values=dict(defaults or {},region=region)
    if '灰度' in request:values['terrain_palette']='gray'
    elif '暖色' in request:values['terrain_palette']='earth'
    elif '自然色' in request:values['terrain_palette']='natural'
    if '关闭经纬网' in request:values['grid_mode']='off'
    level=re.search(r'(?:级别|zoom)\s*(\d{1,2})(?!\d)',request,re.I)
    if level:values['zoom']=int(level[1])
    plan=validate_plan(values)
    plan['unmet_requirements']=requirement_gaps(request)
    return plan


def handle_request(request):
    op=request.get('operation')
    if op=='plan':
        if request.get('endpoint') and request.get('model'):
            return request_plan(request['request'],request['endpoint'],request['model'],request.get('key',''),request.get('parameters'))
        return rule_plan(request['request'],request.get('region_hint',''),request.get('parameters'))
    if op=='search':
        from .online import search_regions
        rows=search_regions(request['region'],Path.home()/'.arcgis-paper-mcp/pro-search')
        return [{k:v for k,v in r.items() if k!='geojson'} for r in rows
                if (r.get('geojson') or {}).get('type') in ('Polygon','MultiPolygon') or r.get('provider')=='geodoi_tp2021']
    if op=='ping':
        from .backend import dispatch
        return dispatch('ping',{})
    if op=='render':
        plan=validate_plan(request['plan'])
        unmet=plan.pop('unmet_requirements')+requirement_gaps(request.get('request',''))
        if unmet:raise ValueError('当前入口不支持：'+'、'.join(dict.fromkeys(unmet)))
        project=Path(request['project'])
        if project.suffix.lower()!='.aprx' or not project.is_file():raise ValueError('请先打开并保存一个 ArcGIS Pro 工程。')
        from .backend import dispatch
        result=dispatch('create_online_map',dict(**plan,output_dir=request['output_dir'],
                        project_path=str(project),osm_id=request['osm_id'],request=request.get('request','')))
        import arcpy
        generated=arcpy.mp.ArcGISProject(result['project'])
        broken=[layer.name for m in generated.listMaps() for layer in m.listLayers() if layer.isBroken]
        if broken:raise ValueError('生成工程存在断开的数据引用，请检查输出目录。')
        pagx=str(Path(result['project']).with_name('paper-map.pagx'))
        generated.listLayouts(result['layout'])[0].exportToPAGX(pagx)
        result['pagx']=pagx
        return result
    raise ValueError('Unsupported pane operation')


def main():
    response=Path(sys.argv[1])
    request={}
    try:
        raw=sys.stdin.buffer.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('Request too large')
        request=json.loads(raw.decode('utf-8-sig'))
        reply={'ok':True,'result':handle_request(request)}
    except Exception as exc:
        error=str(exc)
        key=request.get('key','')
        if key:error=error.replace(key,'[已隐藏]')
        reply={'ok':False,'error':error}
    # The caller reads only after process exit: no concurrent reader and no rename needed.
    # Some EFS/redirected AppData folders reject os.replace(tmp, response) with WinError17.
    response.parent.mkdir(parents=True,exist_ok=True)
    response.write_text(json.dumps(reply,ensure_ascii=False,allow_nan=False),encoding='utf-8')


if __name__=='__main__':main()
