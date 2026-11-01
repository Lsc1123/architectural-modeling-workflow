import asyncio
import sys
from mcp import Client, StdioServerParameters


def test_real_stdio_discovery_and_state_operations(tmp_path):
    async def run():
        params=StdioServerParameters(command=sys.executable,args=['-m','amw.cli','serve','--workspace',str(tmp_path)])
        async with Client(params) as client:
            tools=await client.list_tools()
            names={x.name for x in tools.tools}
            assert {'project_init','sketchup_create','asset_build','checks_run','handoff_export'}<=names
            result=await client.call_tool('project_init',{'name':'protocol fixture'})
            assert result.structured_content['name']=='protocol fixture'
            result=await client.call_tool('project_get',{})
            assert result.structured_content['stage']=='exploration'
            result=await client.call_tool('get_capabilities',{})
            assert result.structured_content['units']=='m'
    asyncio.run(run())
