"""CLI for MCP, configuration checks and direct ArcGIS Python execution."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import hydrology_config, load_config


def main():
    parser = argparse.ArgumentParser(description='ArcGIS Paper MCP — editable scientific maps')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('serve',help='Start MCP stdio server')
    sub.add_parser('ping',help='Check ArcPy in this Python environment')
    for name in ('validate','render'):
        sub.add_parser(name).add_argument('config')
    sub.add_parser('inspect').add_argument('path')
    demo = sub.add_parser('demo',help='Generate clearly labelled synthetic sample data (ArcGIS Python required)')
    demo.add_argument('output_dir')
    demo.add_argument('--project',required=True,help='Existing APRX used as read-only seed')
    demo.add_argument('--world',help='Optional local world polygon data')
    demo.add_argument('--country',help='Optional local country polygon data')
    hydro = sub.add_parser('hydrology')
    hydro.add_argument('dem')
    hydro.add_argument('output_dir')
    hydro.add_argument('--threshold-km2',type=float,required=True)
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            from .server import main as serve
            serve()
            return
        if args.command == 'validate':
            result = load_config(args.config)
        elif args.command == 'demo':
            from .demo import create_demo
            result = create_demo(args.output_dir,args.project,args.world,args.country)
        else:
            from .backend import dispatch
            if args.command == 'render':
                result = dispatch('render_map',{'config':load_config(args.config)})
            elif args.command == 'hydrology':
                cfg = hydrology_config({'dem':args.dem,'output_dir':args.output_dir,'threshold_km2':args.threshold_km2},Path.cwd())
                result = dispatch('derive_hydrology',{'config':cfg})
            elif args.command == 'inspect':
                result = dispatch('inspect_data',{'path':args.path})
            else:
                result = dispatch('ping',{})
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}',file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
