"""Loopback-only real Watch app with an isolated synthetic DB; no production config."""
import asyncio
from pathlib import Path
import sys
import tempfile
import argparse
from unittest.mock import patch
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from discordbot.platform.clock import SystemClock, Uuid4Generator
from discordbot.platform.telemetry import TelemetryBuffer, TelemetryEmitter
from discordbot.storage.adapters.execution import SqliteDatabase
from discordbot.storage.adapters.recovery import DataRecovery
from discordbot.storage.ports.contracts import DatabaseConfig, DatabaseRequest
from discordbot.watch.adapters.security import Capabilities
from discordbot.watch.adapters.writer import SqliteWatchWriter
from discordbot.watch.adapters.web import build_public_app
from discordbot.watch.application.service import WatchService
from discordbot.watch.domain.policy import WatchLimits

class Metadata:
    async def title(self, identity): return 'Synthetic browser fixture'
    async def close(self): pass

async def main(template: Path | None = None):
    work = ROOT / 'scratch/watch-browser'
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='synthetic-', dir=work) as tmp:
        db = SqliteDatabase(DatabaseConfig(Path(tmp)/'synthetic.db'))
        await DataRecovery(db).bootstrap(DatabaseRequest.within(10))
        await db.start()
        clock = SystemClock()
        service = WatchService(SqliteWatchWriter(db), Capabilities('synthetic-browser-only-key-32-characters'),
            Metadata(), WatchLimits(), clock, Uuid4Generator(),
            TelemetryEmitter(buffer=TelemetryBuffer(128), clock=clock, service='watch-web', environment='test', release='synthetic'))
        await service.start(); service.schedule()
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            if template and path.name == 'player.html':
                return original_read(template, *args, **kwargs)
            return original_read(path, *args, **kwargs)
        with patch.object(Path, 'read_text', read):
            app = build_public_app(service, 'http://127.0.0.1:8765')
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8765, log_level='critical', access_log=False))
        serial = 0
        @app.post('/fixture/new')
        async def new():
            nonlocal serial
            serial += 1
            invite = await service.create(100, 42, 'browser-'+str(serial), int(service.now()))
            return {'capability': invite.capability}
        @app.get('/fixture/state')
        async def state():
            return {'rooms': len(service.sessions), 'clients': sum(len(a.peers) for a in service.sessions.values()),
                'states': [{'closed': a.closed, 'clients': len(a.peers), 'unique_clients': len(set(a.peers)),
                    'has_video': 'videoId' in a.playback, 'state': a.playback.get('state'),
                    'position': a.playback_snapshot().get('time'), 'revision': a.revision} for a in service.sessions.values()]}
        @app.post('/fixture/close')
        async def close():
            for sid in tuple(service.sessions): await service.close(sid)
            return {'closed': True}
        @app.post('/fixture/shutdown')
        async def shutdown():
            server.should_exit = True
            return {'stopping': True}
        try:
            await server.serve()
        finally:
            await service.stop(); await db.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', type=Path, help='Offline pre-fix HTML for FAIL-to-PASS comparison')
    args = parser.parse_args()
    asyncio.run(main(args.template))
