"""Inspect systemd credential metadata only; never read or print credential values."""

import json
import os
import subprocess
from pathlib import Path


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Interactive sudo required")
    code = '''import json,os,pathlib,stat,struct
root=pathlib.Path('/run/credentials/discordbot-credential-probe.service')
result={'uid':os.geteuid(),'gid':os.getegid(),'readonly':bool(os.statvfs(root).f_flag & os.ST_RDONLY)}
for label,path in [('directory',root),('file',root/'db_key')]:
 info=path.stat()
 result[label]={'mode':oct(stat.S_IMODE(info.st_mode)),'uid':info.st_uid,'gid':info.st_gid,'regular':stat.S_ISREG(info.st_mode)}
 try:
  raw=os.getxattr(path,'system.posix_acl_access')
  result[label]['acl_version']=struct.unpack('<I',raw[:4])[0]
  result[label]['acl_entries']=[{'tag':tag,'permissions':perm,'id':identity} for tag,perm,identity in struct.iter_unpack('<HHI',raw[4:])]
 except OSError as error:
  result[label]['acl_errno']=error.errno
print(json.dumps(result))
'''
    command = ["systemd-run", "--wait", "--pipe", "--collect", "--unit=discordbot-credential-probe",
               "--property=User=discordbot-deploy", "--property=Group=discordbot",
               "--property=LoadCredential=db_key:/etc/discordbot/secrets/db_key",
               "--property=RuntimeMaxSec=30", "/usr/bin/python3", "-I", "-c", code]
    result = subprocess.run(command, capture_output=True, text=True, timeout=45)
    output = Path("/home/os/discordbot-phase9/credential-probe.json")
    output.write_text(json.dumps({"returncode":result.returncode,"metadata":result.stdout.strip()},indent=2))
    output.chmod(0o644)
    print(output.read_text(), flush=True)
