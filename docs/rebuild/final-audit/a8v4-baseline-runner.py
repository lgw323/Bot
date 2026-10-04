"""Run the unchanged original probe against exact pre-M4 modules in memory."""
from pathlib import Path
import runpy
import subprocess
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
runpy.run_path(str(ROOT / 'conftest.py'))
from discordbot.operations import adapters

BASELINE = 'ecc7674a59150c280bca15031f51eb7ec1015a7a'
policy = ModuleType('a8v4_baseline_policy')
old = ModuleType('a8v4_baseline_probe')
for target, name in ((policy, 'probe_policy'), (old, 'probe')):
    path = f'src/discordbot/operations/adapters/{name}.py'
    source = subprocess.check_output(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT)
    exec(compile(source, f'{BASELINE}:{path}', 'exec'), target.__dict__)
old.ProbePolicy = policy.ProbePolicy
sys.modules['discordbot.operations.adapters.probe'] = old
adapters.probe = old
runpy.run_path(str(Path(__file__).with_name('a8r4-test-runner.py')), run_name='__main__')
