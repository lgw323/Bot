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
import hashlib

EVENTS={'music.request_received','music.ui_failed','music.command_failed','music.work_started','music.work_failed',
        'summary.request','summary.response','summary.preload',
        'music.work_succeeded','music.voice_connected','music.enqueued','music.media_acquisition_started',
        'music.media_acquired','music.cache_leased','music.ffmpeg_started','music.first_pcm',
        'music.smoke_failed','music.playback_accepted','music.playback_ended','music.decoder_failed','database.probe_failed',
        'task.failed','task.deadline_exceeded','task.retrying', 'database.probe_contention','database.probe_recovered'}
STAGES={'ui_request','request','message_request','action','selection','connect','enqueue','lookup','started','ended',
        'result','tts','leave','close','control','prepare','autoplay','retry','start','reconnect','empty','join-tts',
        'live_smoke','voice_connection','media_acquisition','cache_lease','ffmpeg_start','first_pcm','voice_playback_acceptance',
        'playback_callback','pcm_decode'}
CODES={'internal','validation','authorization','capacity','conflict','data_integrity','database_unavailable',
       'deadline_exceeded','external_temporary','external_permanent','shutdown','not_found'}


REASONS = {'executable_not_found','process_start_failure','process_io_failure','child_nonzero','provider_rejected',
    'auth_required','no_audio_format','download_failed','http_forbidden','timeout','invalid_output','empty_output',
    'cache_read_failure','cache_write_failure','cache_publish_failure','output_limit','js_runtime_missing',
    'http_rate_limited','http_server_error','http_rejected','transport_error'}

def probe_metadata(event):
    # Standalone system Python observer: explicit finite allowlist, no package import required.
    result={}
    options={
        'operation':{'select1_probe'},
        'stage':set('probe_open probe_configure probe_begin probe_execute probe_fetch probe_commit probe_close probe_admission'.split()),
        'exception_family':set('sqlite_operational sqlite_integrity sqlite_database sqlite_other permission os deadline cancellation app unexpected'.split()),
        'sqlite_family':set('busy locked io cantopen perm readonly full corrupt notadb constraint interrupt schema other'.split()),
        'errno_category':set('access missing io readonly space capacity other'.split()),
        'probe_disposition':{'bounded_busy','hard','recovery_expired'}}
    for key,allowed in options.items():
        if isinstance(event.get(key),str) and event[key] in allowed: result[key]=event[key]
    for key in ('connection_opened','close_succeeded','cleanup_failed'):
        if type(event.get(key)) is bool: result[key]=event[key]
    code=event.get('sqlite_errorcode')
    if type(code) is int and 0<=code<=0xFFFFFF: result['sqlite_errorcode']=code
    if event.get('healthy_probes')==2: result['healthy_probes']=2
    return result


def bounded_probe_busy(event):
    return (event.get('event')=='database.probe_contention' and event.get('error_code')=='database_unavailable'
        and event.get('probe_disposition')=='bounded_busy' and event.get('operation')=='select1_probe'
        and event.get('stage')=='probe_configure' and type(event.get('sqlite_errorcode')) is int
        and event['sqlite_errorcode']==5 and event.get('sqlite_family')=='busy'
        and event.get('exception_family')=='sqlite_operational' and event.get('connection_opened') is True
        and event.get('close_succeeded') is True and event.get('cleanup_failed') is False)


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
            if name not in EVENTS and event.get('error_code') in {'data_integrity', 'database_unavailable'}:
                name='runtime.integrity_failed'
                event=dict(event,event=name)
            if name=='runtime.integrity_failed':
                counts[name]+=1
                codes[event['error_code']]+=1
                sequence.append({'event':name,'error_code':event['error_code']})
                continue
            if name not in EVENTS: continue
            counts[name]+=1
            value={'event':name}
            if event.get('stage') in STAGES: value['stage']=event['stage']
            if event.get('error_code') in CODES:
                value['error_code']=event['error_code']
                if not bounded_probe_busy(event): codes[event['error_code']]+=1
            if event.get('result') in CODES | {'completed','failed','hit','published','success','delivery_failed','cancellation'}:
                value['result']=event['result']
                if event['result'] in {'data_integrity','database_unavailable'} and event.get('error_code')!=event['result']:
                    codes[event['result']]+=1
            if re.fullmatch('[0-9a-f]{32}',str(event.get('work_id',''))): value['work_id']=event['work_id']
            if event.get('reason') in REASONS: value['reason']=event['reason']
            code=event.get('child_exit_code')
            if type(code) is int and -255<=code<=255: value['child_exit_code']=code
            status=event.get('http_status')
            if type(status) is int and 100<=status<=599: value['http_status']=status
            if name.startswith('database.probe_'): value.update(probe_metadata(event))
            sequence.append(value)
        except (ValueError,TypeError,AttributeError):
            continue
    return {'event_counts':dict(counts),'error_codes':dict(codes),'priorities':dict(priorities),
            'recent_stages':sequence[-100:],'journal_exit_code':result.returncode,
            'possibly_truncated':len(result.stdout.splitlines())>=10000}


def failure_trigger(events):
    for event in events:
        name=event['event']
        if (name=='music.smoke_failed' or name=='music.decoder_failed'
                or name=='music.work_failed' and event.get('stage') in {'lookup','prepare','start','tts'}
                or name=='music.playback_ended' and event.get('result')=='failed'
                or name=='music.command_failed' and event.get('stage')=='connect'):
            return 'music_failure'
        if (name=='summary.request' and event.get('result') in
                {'external_temporary','external_permanent','deadline_exceeded','internal','database_unavailable','data_integrity'}
                or name=='summary.response' and event.get('result')=='delivery_failed'):
            return 'summary_failure'
    return None


def full_sweep_failures(diagnostic):
    """Classify safe metadata only; never issue a provider request or retry."""
    hard=next((code for code in ('data_integrity','database_unavailable')
               if diagnostic.get('error_codes',{}).get(code)),None)
    if diagnostic.get('event_counts',{}).get('database.probe_failed'):
        hard=hard or 'database_probe_failed'
    if diagnostic.get('journal_exit_code') or diagnostic.get('possibly_truncated'):
        hard=hard or 'diagnostic_coverage_lost'
    if diagnostic.get('event_counts',{}).get('task.retrying'):
        hard=hard or 'automatic_retry_during_sweep'
    soft=[]
    for event in diagnostic.get('recent_stages',[]):
        if bounded_probe_busy(event):
            continue
        if event.get('event')=='database.probe_failed':
            hard=hard or 'database_probe_failed'
        if event.get('error_code') in {'data_integrity','database_unavailable'} or event.get('result') in {'data_integrity','database_unavailable'}:
            hard=hard or 'data_integrity'
        elif event.get('event')=='task.retrying':
            hard=hard or 'automatic_retry_during_sweep'
        elif (failure_trigger([event]) or event.get('event') in {'music.ui_failed','music.command_failed'}
              or event.get('result') in {'failed','delivery_failed'}):
            soft.append({key:event[key] for key in ('event','stage','error_code','result','reason','http_status') if key in event})
    return hard,soft


def health_trigger(value, first, release, bad):
    if any(h.get('metrics',{}).get('database_probe_recovery_pending')==1 and not h.get('ready')
           for h in value.get('health',{}).values()):
        return 'probe_recovery_readiness_lost'
    for name in ('discord-bot.service','watch-web.service'):
        state=value.get('services',{}).get(name,{})
        initial=first.get('services',{}).get(name,{})
        if (state.get('ActiveState')!='active' or state.get('MainPID','0')=='0'
                or state.get('Result')!='success' or state.get('NRestarts')!=initial.get('NRestarts')):
            return 'service_crash_or_restart'
    if any(h.get('release')!=release for h in value.get('health',{}).values()):
        return 'release_mismatch'
    if bad>=3:
        return 'persistent_readiness_loss'
    return None


def file_inventory(directory):
    rows=[]
    for path in sorted(directory.rglob('*')):
        if path.is_symlink(): raise RuntimeError('linked_preservation_input')
        if path.is_file():
            with path.open('rb') as stream:
                rows.append((str(path.relative_to(directory)),hashlib.file_digest(stream,'sha256').hexdigest()))
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()


SWEEP_GATES=('startup','gateway','command_sync','profile','ranking','summary','favorites','volume',
    'music_url','music_search','selection','queue','music_audible','stop','voice_disconnect',
    'tts_audible','tts_not_overwritten','music_after_tts','tts_pause','watch_create','watch_connect',
    'watch_presence','watch_refresh','watch_reconnect','watch_tab_return','watch_hydration','watch_sync',
    'watch_close','admin_close','public_browser')


def handoff_ready(control,release,common,soft_failures):
    """Explicit human results plus an already running replacement guard; never infer PASS."""
    path=control/'all-gates-pass.json'
    if not path.exists() or soft_failures: return False
    data=json.loads(path.read_text())
    if (data.get('release')!=release or data.get('gates')!={gate:'PASS' for gate in SWEEP_GATES}
            or data.get('human_audio_confirmed') is not True or data.get('chrome_confirmed') is not True):
        return False
    unit=data.get('replacement_guard','')
    if not re.fullmatch('phase10-retry-'+re.escape(release[2:18])+'-post-cutover-[a-z0-9-]{1,48}\\.service',unit):
        return False
    state=common.systemd(unit)
    return state.get('ActiveState')=='active' and state.get('MainPID','0')!='0' and state.get('NRestarts')=='0'


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
        for name in ('data','state','cache','backups','audit'):
            if file_inventory(common.ROOT/name)!=file_inventory(destination/name):
                raise RuntimeError('preserved_inventory_mismatch')
        if file_inventory(Path('/etc/discordbot'))!=file_inventory(destination/'etc-discordbot'):
            raise RuntimeError('preserved_configuration_mismatch')
    return {'pair_stopped':True,'newest_state_preserved':True,'inventory_verified':True}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',required=True)
    parser.add_argument('--seconds',type=int,required=True)
    parser.add_argument('--suffix',choices=('live-smoke','post-cutover'),required=True)
    parser.add_argument('--install',action='store_true')
    parser.add_argument('--since-unix',type=float)
    parser.add_argument('--policy',choices=('strict','full-sweep'),default='strict')
    parser.add_argument('--run-id')
    args=parser.parse_args()
    if os.geteuid()!=0 or not re.fullmatch('r-[0-9a-f]{16}-[0-9a-f]{16}',args.release) or not 60<=args.seconds<=1800:
        raise SystemExit('root_and_bounded_reviewed_release_required')
    if args.since_unix is not None and not 0<=time.time()-args.since_unix<=3600:
        raise SystemExit('recent_observation_window_required')
    if args.run_id is not None and not re.fullmatch('[a-z0-9-]{1,48}',args.run_id):
        raise SystemExit('Invalid unique run identity')
    if args.policy=='full-sweep' and (not args.run_id or args.suffix!='live-smoke'):
        raise SystemExit('Full sweep requires unique live-smoke run')
    label='phase10-retry-'+args.release[2:18]+'-'+args.suffix+('-'+args.run_id if args.run_id else '')
    output=Path('/var/tmp')/label
    preservation=Path('/var/lib/discordbot')/(label+'-guard-preservation')
    source=Path('/opt/discordbot/releases')/args.release/'app'
    spec=importlib.util.spec_from_file_location('reviewed_observation',source/'deploy/staging/observe.py')
    common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common)
    if args.policy=='full-sweep':
        sys.path.insert(0,str(source/'src'))
        from discordbot.composition.live_validation import full_sweep_active
        safety_spec=importlib.util.spec_from_file_location('sweep_safety',source/'deploy/production/sweep-safety.py')
        safety=importlib.util.module_from_spec(safety_spec);safety_spec.loader.exec_module(safety)
        if not full_sweep_active(args.release):
            raise SystemExit('Finite root-owned full-sweep marker required')
    if args.install:
        marker=Path('/run/discordbot-live-smoke')
        if not marker.is_file() or marker.is_symlink() or marker.stat().st_uid!=0:
            raise SystemExit('Root-owned live-smoke admission marker required')
        output.mkdir(mode=0o755);output.chmod(0o755)
        preservation.mkdir(mode=0o700);preservation.chmod(0o700)
        if args.policy=='full-sweep':
            import pwd
            control=output/'control';control.mkdir(mode=0o700)
            operator=pwd.getpwnam('os');os.chown(control,operator.pw_uid,operator.pw_gid)
        target=output/Path(__file__).name
        shutil.copyfile(__file__,target);target.chmod(0o444)
        subprocess.run(['systemd-run','--collect','--unit='+output.name,'-p','RuntimeMaxSec='+str(args.seconds+180),
            '-p','TimeoutStopSec=100','-p','UMask=0022','-p','ProtectSystem=strict','-p','ProtectHome=yes',
            '-p','ReadWritePaths='+str(output)+' '+str(preservation)+' /var/lib/discordbot/operations.lock',
            '/usr/bin/python3','-I','-B',str(target),
            '--release',args.release,'--seconds',str(args.seconds),'--suffix',args.suffix,
            '--since-unix',str(args.since_unix or time.time()),'--policy',args.policy,
            *(['--run-id',args.run_id] if args.run_id else [])],
            check=True,capture_output=True,timeout=15)
        print('Finite '+args.suffix+' observation started.')
        return
    try:
        observe_loop(args, source, output, preservation, common,
                     safety if args.policy=='full-sweep' else None,
                     full_sweep_active if args.policy=='full-sweep' else None)
    except Exception as error:
        # A failed observer must not leave an unguarded production pair.
        if args.policy=='full-sweep':
            failure={'status':'guard_requires_reconciliation','error_type':type(error).__name__}
            try:
                failure['guard']=preserve_failure(preservation,common)
            except Exception as stop_error:
                failure['stop_error_type']=type(stop_error).__name__
            try:
                common.write_json(output/'observer-error.json',failure)
            except OSError:
                # Evidence storage itself failed; report only the fixed safe status.
                print('Observer evidence unavailable; stopped-state reconciliation required.')
            raise SystemExit('Full-sweep observer failed; stopped-state reconciliation required.') from None
        raise


def observe_loop(args, source, output, preservation, common, safety=None, full_sweep_active=None):
    common.METRICS.update({'music_actors','music_cache_bytes','music_processes','watch_sessions','watch_clients',
                           'database_probe_recovery_pending'})
    started=time.monotonic();since=args.since_unix or time.time();first=None;count=bad=0;status='observing';last_diagnostics={}
    sampled_at=-5
    soft_failures=[]
    safety_baseline=safety.identity(source) if args.policy=='full-sweep' else None
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
        failure=failure_trigger(last_diagnostics['recent_stages'])
        if args.policy=='full-sweep':
            failure,soft=full_sweep_failures(last_diagnostics)
            for item in soft:
                if item not in soft_failures: soft_failures.append(item)
            if len(soft_failures)>256: failure=failure or 'diagnostic_capacity_exceeded'
            failure=failure or health_trigger(value,first,args.release,bad)
            if fresh:
                try:
                    value['safety']=safety.check(source,common,value,safety_baseline)
                except Exception as error:
                    failure=failure or 'safety_invariant_failed'
                    value['safety']={'error_type':type(error).__name__}
                    if str(error) in safety.SAFE_FAILURES:
                        value['safety']['reason']=str(error)
            if not full_sweep_active(args.release): failure=failure or 'validation_window_expired'
            control=output/'control'
            if (control/'emergency-stop').exists(): failure='operator_emergency_stop'
            if not failure and handoff_ready(control,args.release,common,soft_failures):
                status='handed_to_post_cutover_guard'
            if (control/'finish').exists() or time.monotonic()-started>=args.seconds:
                failure=failure or 'sweep_finished_or_deadline'
        if unsafe or mismatch or bad>=3 or failure:
            status='guard_stopped_pair'
            value['guard_trigger']=failure or 'health_or_restart'
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
            'requested_seconds':args.seconds,'first':first,'last':value,'diagnostics':last_diagnostics,
            'policy':args.policy,'soft_failures':soft_failures})
        if status!='observing': return
        time.sleep(min(.25,args.seconds-elapsed))


if __name__=='__main__':
    main()
