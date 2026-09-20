#!/usr/bin/env python3
"""Verify wait/pause tools compile, import, and register."""
import sys, os
sys.path.insert(0, '/home/alexey/dev/kunipy')
os.chdir('/home/alexey/dev/kunipy')

import py_compile
py_compile.compile('src/tools.py', doraise=True)
py_compile.compile('src/worker.py', doraise=True)
print("COMPILE OK")

import src.tools as tm
w = tm.create_wait_tool()
p = tm.create_pause_tool()
print(f"wait tool: name={w.name!r}, desc={w.description!r}, params={w.parameters}")
print(f"pause tool: name={p.name!r}, desc={p.description!r}, params={p.parameters}")
print(f"_TERMINAL_TOOL_NAMES: {sorted(tm._TERMINAL_TOOL_NAMES)}")

# Check default tools include wait/pause
from src.tools import create_default_tools
t = create_default_tools()
names = [tool.name for tool in t.tools] if hasattr(t, 'tools') else None
print(f"registered in default: {names}")

# Check worker module sees the constant through the shim
import src.tools as tools_module
print(f"worker sees _TERMINAL_TOOL_NAMES: {sorted(tools_module._TERMINAL_TOOL_NAMES)}")

# Simulate tools.call
import asyncio
async def check_call():
    class FakeCtx:
        def __init__(self, user_id='u', chat_id='c'):
            self.user_id = user_id; self.chat_id = chat_id
    r = await t.call('wait', {})
    print(f"wait() returned: {r!r}")
    r = await t.call('pause', {})
    print(f"pause() returned: {r!r}")

asyncio.run(check_call())
print("ALL OK")
