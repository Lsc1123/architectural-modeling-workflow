import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path
from . import __version__


def main():
    p=argparse.ArgumentParser(prog='amw',description='Architectural Modeling Workflow MCP')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ['serve','doctor','config']:
        s=sub.add_parser(name);s.add_argument('--workspace',required=True);s.add_argument('--blender',default='/Applications/Blender.app/Contents/MacOS/Blender')
    args=p.parse_args();workspace=str(Path(args.workspace).expanduser().resolve())
    if args.command=='serve':
        from .server import create_server
        create_server(workspace,args.blender).run(transport='stdio')
    elif args.command=='doctor':
        from .native import Native
        print(json.dumps(dict(version=__version__,python=sys.version,platform=platform.platform(),sdk=importlib.metadata.version('mcp'),workspace=workspace,blender=Path(args.blender).is_file(),native=Native(workspace).state()),ensure_ascii=False,indent=2))
    else:
        print(json.dumps({'mcpServers':{'architectural-modeling-workflow':{'command':sys.executable,'args':['-m','amw.cli','serve','--workspace',workspace,'--blender',args.blender]}}},indent=2))


if __name__=='__main__':main()
