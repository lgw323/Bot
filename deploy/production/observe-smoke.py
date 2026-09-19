"""Finite production health guard and allowlisted diagnostic evidence."""
import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

EVENTS={'music.request_received','music.ui_failed','music.command_failed','music.work_started','music.work_failed',
        'music.work_succeeded','music.voice_connected','music.enqueued','music.media_acquisition_started',
        'music.media_acquired','music.cache_leased','music.ffmpeg_started','music.first_pcm',
        'music.smoke_failed','music.playback_accepted','music.playback_ended','music.decoder_failed','database.probe_failed',
        'task.failed','task.deadline_exceeded','task.retrying'}
STAGES={'ui_request','request','message_request','action','selection','connect','enqueue','lookup','started','ended',
        'result','tts','leave','close','control','prepare','autoplay','retry','start','reconnect','empty','join-tts',
        'live_smoke','voice_connection','media_acquisition','cache_lease','ffmpeg_start','first_pcm','voice_playback_acceptance',
        'playback_callback','pcm_decode'}
CODES={'internal','validation','authorization','capacity','conflict','data_integrity','database_unavailable',
       'deadline_exceeded','external_temporary','external_permanent','shutdown','not_found'}


REASONS = {'executable_not_found','process_start_failure','process_io_failure','child_nonzero','provider_rejected',
    'auth_required','no_audio_format','download_failed','http_forbidden','timeout','invalid_output','empty_output',
    'cache_read_failure','cache_write_failure','cache_publish_failure','output_limit','js_runtime_missing'}

def diagnostics(since):
    result=subprocess.run(['journalctl','-u','discord-bot','-u','watch-web','--since=@'+str(int(since)),
        '--no-pager','--quiet','-n','10000','--output=json','--output-fields=PRIORITY,MESSAGE'],
        capture_output=True,text=True,timeout=15)
    counts=Counter(); codes=Counter(); sequence=[]; priorities=Counter()
    for line in result.stdout.splitlines():
        try:
            row=json.loads(line)
            priority=str(row.get('PRIORITY','unknown'))
            priorities[priority if priority in set('01234567') else 'unknown']+=1
            event=json.loads(row.get('MESSAGE',''))
            name=event.get('event')
            if name not in EVENTS: continue
            counts[name]+=1
            value={'event':name}
            if event.get('stage') in STAGES: value['stage']=event['stage']
            if event.get('error_code') in CODES:
                value['error_code']=event['error_code'];codes[event['error_code']]+=1
            if event.get('result') in {'completed','failed','hit','published'}: value['result']=event['result']
            if re.fullmatch('[0-9a-f]{32}',str(event.get('work_id',''))): value['work_id']=event['work_id']
            if event.get('reason') in REASONS: value['reason']=event['reason']
            code=event.get('child_exit_code')
            if type(code) is int and -255<=code<=255: value['child_exit_code']=code
            sequence.append(value)
        except (ValueError,TypeError,AttributeError):
            continue
    return {'event_counts':dict(counts),'error_codes':dict(codes),'priorities':dict(priorities),
            'recent_stages':sequence[-100:],'journal_exit_code':result.returncode,
            'possibly_truncated':len(result.stdout.splitlines())>=10000}


def preserve_failure(destination, common):
    import fcntl
    timers=['discordbot-'+name+'.timer' for name in ('backup','update','manual')]
    units=['discord-bot.service','watch-web.service','discordbot-staging-discord.service',
           'discordbot-backup.service','discordbot-update.service','discordbot-manual.service']
    subprocess.run(['systemctl','disable','--now',*timers,*units[:3]],capture_output=True,check=True,timeout=100)
    subprocess.run(['systemctl','stop',*units[3:]],capture_output=True,check=True,timeout=100)
    for unit in units:
        state=common.systemd(unit)
        if state['ActiveState']!='inactive' or state['MainPID']!='0':
            raise RuntimeError('stop_unconfirmed')
    with (common.ROOT/'operations.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        for name in ('data','state','cache','backups','audit'):
            shutil.copytree(common.ROOT/name,destination/name,copy_function=shutil.copy2)
        shutil.copytree(Path('/etc/discordbot'),destination/'etc-discordbot',copy_function=shutil.copy2)
        (destination/'release.txt').write_text(str(Path('/opt/discordbot/current').resolve(strict=True)))
        subprocess.run(['sync','-f',str(destination)],capture_output=True,check=True,timeout=30)
    return {'pair_stopped':True,'newest_state_preserved':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',required=True)
    parser.add_argument('--seconds',type=int,required=True)
    parser.add_argument('--suffix',choices=('live-smoke','post-cutover'),required=True)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--since-unix',type=float)
    args=parser.parse_args()
    if os.geteuid()!=0 or not re.fullmatch('r-[0-9a-f]{16}-[0-9a-f]{16}',args.release) or not 60<=args.seconds<=1800:
        raise SystemExit('root_and_bounded_reviewed_release_required')
    if args.since_unix is not None and not 0<=time.time()-args.since_unix<=3600:
        raise SystemExit('recent_observation_window_required')
    output=Path('/var/tmp')/('phase10-retry-'+args.release[2:18]+'-'+args.suffix)
    preservation=Path('/var/lib/discordbot')/('phase10-retry-'+args.release[2:18]+'-'+args.suffix+'-guard-preservation')
    source=Path('/opt/discordbot/releases')/args.release/'app'
    spec=importlib.util.spec_from_file_location('reviewed_observation',source/'deploy/staging/observe.py')
    common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    if args.install:
        marker=Path('/run/discordbot-live-smoke')
        if not marker.is_file() or marker.is_symlink() or marker.stat().st_uid!=0:
            raise SystemExit('Root-owned live-smoke admission marker required')
        output.mkdir(mode=0o755);output.chmod(0o755)
        preservation.mkdir(mode=0o700);preservation.chmod(0o700)
        target=output/Path(__file__).name
        shutil.copyfile(__file__,target);target.chmod(0o444)
        subprocess.run(['systemd-run','--collect','--unit='+output.name,'-p','RuntimeMaxSec='+str(args.seconds+180),
            '-p','TimeoutStopSec=100','-p','UMask=0022','-p','ProtectSystem=strict','-p','ProtectHome=yes',
            '-p','ReadWritePaths='+str(output)+' '+str(preservation)+' /var/lib/discordbot/operations.lock',
            '/usr/bin/python3','-I','-B',str(target),
            '--release',args.release,'--seconds',str(args.seconds),'--suffix',args.suffix,
            '--since-unix',str(args.since_unix or time.time())],
            check=True,capture_output=True,timeout=15)
        print('Finite '+args.suffix+' observation started.')
        return
    common.METRICS.update({'music_actors','music_cache_bytes','music_processes','watch_sessions','watch_clients'})
    started=time.monotonic();since=args.since_unix or time.time();first=None;count=bad=0;status='observing';last_diagnostics={}
    sampled_at=-5
    while True:
        fresh=time.monotonic()-started-sampled_at>=5
        if fresh:
            value=common.sample();sampled_at=time.monotonic()-started
        first=first or value;count+=1
        states=value['services']
        unsafe=any(states.get(name,{}).get('NRestarts')!=first['services'].get(name,{}).get('NRestarts')
                   for name in ('discord-bot.service','watch-web.service'))
        health=value['health']
        mismatch=any(h.get('release')!=args.release for h in health.values())
        good=len(health)==2 and all(h.get('ready') for h in health.values())
        if fresh: bad=0 if good else bad+1
        last_diagnostics=diagnostics(since)
        music_failure=any(event['event']=='music.smoke_failed' or (event['event']=='music.work_failed' and event.get('stage') in {'lookup','prepare','start','tts'})
            or (event['event']=='music.playback_ended' and event.get('result')=='failed')
            or event['event']=='music.decoder_failed'
            or (event['event']=='music.command_failed' and event.get('stage')=='connect')
            for event in last_diagnostics['recent_stages'])
        if unsafe or mismatch or bad>=3 or music_failure:
            status='guard_stopped_pair'
            value['guard_trigger']='music_failure' if music_failure else 'health_or_restart'
            try:
                value['guard']=preserve_failure(preservation,common)
            except Exception as error:
                status='guard_requires_reconciliation'
                value['guard']={'error_type':type(error).__name__}
        with (output/'samples.jsonl').open('a') as stream:
            stream.write(json.dumps(value)+'\n');stream.flush();os.fsync(stream.fileno())
        elapsed=time.monotonic()-started
        if count%3==1 or status!='observing' or elapsed>=args.seconds:
            last_diagnostics=diagnostics(since)
        if elapsed>=args.seconds and status=='observing': status='complete'
        common.write_json(output/'summary.json',{'status':status,'samples':count,'observed_seconds':round(elapsed,3),
            'requested_seconds':args.seconds,'first':first,'last':value,'diagnostics':last_diagnostics})
        if status!='observing': return
        time.sleep(min(.25,args.seconds-elapsed))


if __name__=='__main__':
    main()
