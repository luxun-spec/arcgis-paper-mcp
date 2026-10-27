"""Actual MCP stdio initialize/list/call, no ArcGIS license required."""
import asyncio
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ProtocolTests(unittest.TestCase):
    def test_tools_are_discoverable_and_callable(self):
        async def check():
            params = StdioServerParameters(command=sys.executable,args=['-m','arcgis_paper_mcp.server'])
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertEqual(names,{'list_templates','validate_map_config','ping_arcgis','inspect_dataset','create_paper_map','derive_watershed'})
                    result = await session.call_tool('list_templates',{})
                    self.assertFalse(result.isError)
                    self.assertIn('study_area',str(result))
                    prompts = await session.list_prompts()
                    self.assertTrue(any(p.name == 'paper_map_workflow' for p in prompts.prompts))
        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
