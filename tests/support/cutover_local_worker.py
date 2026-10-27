"""Fixed local-only executable model. No auth/SSH/systemctl or child spawning."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import time
from urllib.parse import unquote,urlparse
import dotenv
import dotenv.main
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
folder=Path(sys.argv[1]).resolve()
mode=sys.argv[2]
# The parent grants this child one fresh synthetic fixture directory.
# Do not tie pytest's tmp_path to a historical scratch checkout.
assert folder.is_dir()
marker = folder / '.cutover-test-owned'
assert marker.read_text(encoding='ascii') == sys.argv[3]
assert len(sys.argv[3]) == 32 and all(c in '0123456789abcdef' for c in sys.argv[3])
assert set(folder.iterdir()) == {marker}, 'fixture must be empty before worker startup'
assert mode in {'success','hang-normalized','readiness-failure','invalid-receipt','sentinel'}
# Installed candidates include src/tests/deploy, but not the root conftest.py.
# Keep this isolated child credential boundary self-contained in both layouts.
for name in tuple(os.environ):
    if name in {'MASTER_USER_ID', 'LOG_CHANNEL_ID', 'SUMMARY_CHANNEL_ID',
                'DEFAULT_SUMMARY_HOURS', 'LOG_RETENTION_HOURS', 'INITIAL_LOAD_HOURS',
                'MAX_LOG_COUNT', 'MAX_HISTORY_FETCH', 'PRUNE_INTERVAL_MINUTES',
                'GEMINI_MODEL', 'TIMEZONE_OFFSET_HOURS', 'DEFAULT_MAX_REQUEST_TOKENS',
                'MAX_RESPONSE_TOKENS', 'TEMPERATURE', 'DEBUG_MODE'} or name.startswith(
                    ('DISCORD_', 'GOOGLE_', 'DB_', 'MUSIC_', 'YTDLP_', 'WATCH_',
                     'APP_', 'PLATFORM_')):
        os.environ.pop(name, None)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
dotenv.load_dotenv = dotenv.main.load_dotenv = lambda *args, **kwargs: False
def guard(event,args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        requested = os.path.abspath(os.fsdecode(args[0]))
        for candidate in (requested, os.path.realpath(requested)):
            if any(part == '.env' or part.startswith('.env.')
                   for part in candidate.replace('\\', '/').split('/')):
                raise PermissionError('worker credential access forbidden')
    if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.gethostbyname'}:
        frame=sys._getframe(1)
        while frame:
            if frame.f_code.co_name in {'socketpair','_fallback_socketpair'} and frame.f_code.co_filename==socket.__file__:
                return
            frame=frame.f_back
        raise PermissionError('application network forbidden')
    if event=='sqlite3.connect':
        name=str(args[0])
        if name==':memory:':return
        if name.startswith('file:'):
            name=unquote(urlparse(name).path)
            if os.name=='nt' and name.startswith('/') and name[2:3]==':':name=name[1:]
        assert Path(name).resolve().is_relative_to(folder),'only explicit synthetic fixture DBs'
sys.addaudithook(guard)
sys.path.insert(0,str(ROOT/'src'))
if mode=='sentinel':
    (folder/'ready').write_text('local-test-owned-sentinel')
    time.sleep(30)
    raise SystemExit(0)
if mode=='invalid-receipt':
    (folder/'controller.json').write_text('SYNTHETIC_UNTRUSTED_DATA'*400)
    (folder/'ready').write_text('local-test-invalid-receipt')
    time.sleep(30)
    raise SystemExit(1)
spec=importlib.util.spec_from_file_location('local_cutover_fixture',ROOT/'tests/integration/operations/cutover_model.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
model=module.Model(folder)
real=model.controller.step
def step(stage,action,**kwargs):
    def wrapped():
        value=action()
        if mode=='hang-normalized' and stage==module.cc.Step.NORMALIZE:
            (folder/'ready').write_text('normalization_returned_pointer_not_attempted')
            time.sleep(30)
        if mode=='readiness-failure' and stage==module.cc.Step.READY:
            raise module.cc.Blocked('synthetic_gate')
        return value
    return real(stage,wrapped,**kwargs)
model.controller.step=step
result=model.controller.run()
print(json.dumps(result.payload()),flush=True)
raise SystemExit(0 if result.status.startswith('LOCAL_') else 1)
