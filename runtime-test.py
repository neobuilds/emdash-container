"""Bounded native-image boot and volume-recreation gate; not full CMS certification."""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

image, arch = sys.argv[1:]
name = 'emdash-image-' + secrets.token_hex(5)
vol = name + '-data'

def docker(*args):
    return subprocess.check_output(['docker', *args], text=True).strip()

try:
    with tempfile.TemporaryDirectory(prefix='emdash-runtime-') as tmp:
        env = Path(tmp) / 'runtime.env'
        env.write_text('EMDASH_ENCRYPTION_KEY_HEX=' + secrets.token_hex(32) + '\nEMDASH_SITE_URL=http://localhost:4321\n')
        env.chmod(0o600)
        for attempt in range(2):
            docker('run', '-d', '--name', name, '--env-file', str(env), '-p', '127.0.0.1::4321', '-v', vol + ':/app/data', image)
            port = docker('port', name, '4321/tcp').split(':')[-1]
            deadline = time.monotonic() + 90
            while True:
                try:
                    response = urllib.request.urlopen('http://127.0.0.1:' + port + '/_emdash/api/setup/status', timeout=5)
                    data = json.load(response)
                    assert response.status == 200 and isinstance(data, dict)
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(2)
            if attempt == 0:
                actual = docker('exec', name, 'node', '-p', 'process.arch')
                assert actual == {'amd64': 'x64', 'arm64': 'arm64'}[arch]
                workerd = docker('exec', name, './node_modules/.bin/workerd', '--version')
                docker('exec', name, 'node', '-e', "require('fs').writeFileSync('/app/data/image-test','persistent')")
            else:
                assert docker('exec', name, 'node', '-p', "require('fs').readFileSync('/app/data/image-test','utf8')") == 'persistent'
            docker('rm', '-f', name)
        Path('runtime-' + arch + '.json').write_text(json.dumps({'image': image, 'architecture': actual, 'workerd': workerd, 'setup_status_http': 200, 'volume_marker_recreation': True, 'full_onboarding': False}, indent=2) + '\n')
finally:
    subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['docker', 'volume', 'rm', vol], check=True, stdout=subprocess.DEVNULL)
