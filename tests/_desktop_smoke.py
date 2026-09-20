"""Smoke test for desktop stubs."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.desktop import DesktopCharacter
from src.desktop.config import DesktopConfig
from src.desktop.bridges import NoOpMemoryBridge, NoOpLLMBridge

async def main():
    # Default config: disabled
    cfg = DesktopConfig(enabled=False)
    char = DesktopCharacter(cfg)
    await char.start()
    assert not char.is_running(), 'should not run when disabled'
    await char.stop()

    # Bridges default to no-op
    m = char._memory
    l = char._llm
    assert await m.recall('hello') == ''
    await m.remember('hello')
    assert await l.generate_response('hi') == ''
    await l.on_message_sent('hi')

    # Enabled-but-stub: still graceful, no heavy imports triggered
    cfg2 = DesktopConfig(enabled=True, model_path='')
    char2 = DesktopCharacter(cfg2, memory_bridge=NoOpMemoryBridge(), llm_bridge=NoOpLLMBridge())
    await char2.start()
    assert char2.is_running()
    await char2.stop()
    assert not char2.is_running()

    # Check no PySide6/cubism/OpenGL imported by desktop package
    forbidden = [m for m in sys.modules if m.split('.')[0] in ('PySide6', 'cubism', 'OpenGL')]
    assert not forbidden, f'heavy deps leaked: {forbidden}'
    print('desktop stubs OK')

asyncio.run(main())
