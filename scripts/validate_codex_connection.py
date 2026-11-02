"""Read-only Codex app-server MCP discovery, without starting an agent turn."""
import argparse
import json
import os
import selectors
import subprocess
import time
from pathlib import Path
from amw.io import atomic


def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--python',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    # Isolate host diagnostics from unrelated user servers and auth/history.
    diagnostic_home=a.output.parent/'codex-host-home';diagnostic_home.mkdir(parents=True,exist_ok=True)
    cmd=['codex','app-server','--stdio']
    name='architectural_modeling_workflow'
    # Preserve the venv interpreter symlink: resolving it bypasses its packages.
    cmd+=['-c',f'mcp_servers.{name}.enabled=true','-c',f'mcp_servers.{name}.command='+json.dumps(str(a.python.expanduser().absolute())),
        '-c',f'mcp_servers.{name}.args='+json.dumps(['-m','amw.cli','serve','--workspace',str(a.workspace.resolve())])]
    with a.output.with_suffix('.stderr.log').open('w') as log:
        process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,bufsize=1,env=dict(os.environ,CODEX_HOME=str(diagnostic_home.resolve())))
        sel=selectors.DefaultSelector();sel.register(process.stdout,selectors.EVENT_READ)
        notifications=[]
        def request(id,method,params):
            process.stdin.write(json.dumps(dict(id=id,method=method,params=params))+'\n');process.stdin.flush();deadline=time.monotonic()+55
            while time.monotonic()<deadline:
                if not sel.select(.5):continue
                line=process.stdout.readline()
                if not line:raise RuntimeError('Codex app-server exited')
                value=json.loads(line)
                if 'method' in value:notifications.append(value)
                if value.get('id')==id:
                    if value.get('error'):raise RuntimeError(value['error'])
                    return value['result']
            raise TimeoutError('Codex host connection still pending')
        try:
            request(1,'initialize',dict(clientInfo=dict(name='amw-readonly-acceptance',version='0.1.0'),capabilities=dict(experimentalApi=True)))
            process.stdin.write('{"method":"initialized"}\n');process.stdin.flush()
            # An ephemeral protocol fixture initializes the host's MCP manager.
            # No model turn is started and no user chat is persisted.
            fixture=request(2,'thread/start',dict(ephemeral=True,cwd=str(a.workspace.resolve())))
            thread_id=fixture['thread']['id']
            selected=[]
            for i in range(45):
                result=request(3+i,'mcpServerStatus/list',dict(threadId=thread_id,detail='full',limit=100))
                selected=[x for x in result['data'] if x['name']==name]
                if selected and len(selected[0]['tools'])>=40:break
                time.sleep(.5)
            capability=request(100,'mcpServer/tool/call',dict(threadId=thread_id,server=name,tool='get_capabilities',arguments={}))
            assert len(selected)==1 and len(selected[0]['tools'])>=40,selected
            assert not capability.get('isError'),capability
            assert capability['structuredContent']['units']=='m'
            atomic(a.output,dict(status='passed',method='Actual Codex app-server starts stdio MCP, discovers tools/resources and calls get_capabilities in an ephemeral protocol fixture; no model turn or persisted user chat',server=selected[0],tool_result=capability,limits='SDK client executes the full native task suites separately; no Codex UI agent turn is claimed'))
            print('Actual Codex host discovered',len(selected[0]['tools']),'AMW tools')
        finally:
            atomic(a.output.with_suffix('.notifications.json'),notifications)
            process.terminate();process.wait(timeout=10)


if __name__=='__main__':main()
