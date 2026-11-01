"""Shared real-MCP acceptance harness; never mock a native application."""
import json
import sys
import asyncio
import time
from pathlib import Path
from mcp import Client, StdioServerParameters
from amw.io import atomic,read,sha
from amw.jobs import adapter_path


class Harness:
    def __init__(self,root,directory,prefix):
        self.root=Path(root).resolve();self.directory=directory;self.prefix=prefix
        self.logs=[];self.revision=None
        self.client=Client(StdioServerParameters(command=sys.executable,args=['-m','amw.cli','serve','--workspace',str(self.root)]))

    async def __aenter__(self):
        await self.client.__aenter__()
        try:
            state=await self.call('sketchup_state')
            if not state.get('connected'):raise RuntimeError('Connect the isolated acceptance workspace in SketchUp first')
            if state.get('bridge_sha256')!=sha(adapter_path('sketchup/amw_bridge.rb')):
                raise RuntimeError('Loaded native bridge differs from this source/package; preserve the document and install/restart the matching bridge first')
        except BaseException:
            await self.client.__aexit__(None,None,None)
            raise
        return self

    async def __aexit__(self,*args):return await self.client.__aexit__(*args)

    async def call(self,tool,expect_failure=False,**args):
        reply=await self.client.call_tool(tool,args);data=reply.structured_content
        # A busy native file read can temporarily stop the five-second heartbeat.
        # Recover the SAME operation, never repeat its write under a new ID.
        if data and data.get('status') in ('queued','running','unknown') and data.get('operation_id') and tool.startswith('sketchup_'):
            oid=data['operation_id'];deadline=time.monotonic()+90
            while data['status'] in ('queued','running','unknown') and time.monotonic()<deadline:
                await asyncio.sleep(.25)
                recovered=await self.client.call_tool('native_job_status',dict(operation_id=oid))
                data=recovered.structured_content
        failed=reply.is_error or (data and data.get('status') in ('failed','unknown'))
        if not data:data=dict(status='failed',content=[getattr(x,'text',str(x)) for x in reply.content])
        if data.get('state') and not data.get('replayed'):self.revision=data['state']['revision']
        if data.get('document_id') and data.get('revision'):self.revision=data['revision']
        self.logs.append(dict(tool=tool,arguments=args,result=data))
        atomic(self.root/self.directory/'operation_log.json',self.logs)
        if expect_failure:
            if not failed:raise AssertionError('Expected refusal from '+tool)
        elif failed:raise RuntimeError(tool+': '+json.dumps(data,ensure_ascii=False))
        return data

    async def write(self,tool,suffix,**args):
        expected=args.pop('expected_revision',self.revision)
        return await self.call(tool,expected_revision=expected,operation_id=self.prefix+'-'+suffix,**args)

    async def snapshot(self,suffix):
        path=self.directory+'/'+suffix+'.json';await self.call('sketchup_export',path=path)
        return read(self.root/path)

    async def script(self,suffix,code,scope=(),new_roots=False,scenes=()):
        relative=self.directory+'/scripts/'+suffix+'.rb';p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(code)
        return await self.write('sketchup_script',suffix,script=relative,scope_ids=list(scope),
            purpose='Acceptance fixture: '+suffix,allow_new_root_entities=new_roots,scene_names=list(scenes))

    async def blank(self,path):
        await self.write('sketchup_new','new-'+Path(path).stem,path=path)
        current=await self.snapshot('template-'+Path(path).stem)
        await self.script('empty-'+Path(path).stem,
            "m=Sketchup.active_model;m.entities.clear!;m.pages.to_a.each{|p|m.pages.erase(p)};m.definitions.purge_unused;m.materials.purge_unused;m.options['UnitsOptions']['LengthFormat']=0;m.options['UnitsOptions']['LengthUnit']=2",
            scope=['root'],scenes=[s['name'] for s in current.get('scenes',[])])

    async def box(self,name,origin,size,kind='solid',semantic_id=None):
        receipt=await self.write('sketchup_create','create-'+name,name=name,kind=kind,
            shape=dict(type='box',origin=origin,size=size),semantic_id=semantic_id)
        return receipt['result']['created_ids'][0]

    async def update(self,changes,reason):
        p=await self.call('project_get')
        return await self.call('project_update',expected_revision=p['revision'],changes=changes,reason=reason)

    async def register(self,report):
        p=await self.call('project_get')
        return await self.call('evidence_register',expected_revision=p['revision'],report=report)

    async def stage(self,target):
        p=await self.call('project_get');gate=await self.call('stage_check',target=target)
        if not gate['ready']:raise AssertionError(gate)
        return await self.call('stage_advance',expected_revision=p['revision'],target=target,reason='Fixed acceptance task card: '+target)
