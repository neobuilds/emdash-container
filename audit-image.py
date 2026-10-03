"""Scan every saved image layer, including deleted files, before publication.
Heuristic credential detection is not a guarantee that arbitrary secrets are absent.
"""
import base64
import hashlib
import io
import json
import urllib.request
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

image, output = sys.argv[1:]
patterns = [
    rb'gh[pousr]_[A-Za-z0-9]{30,}',
    rb'github_pat_[A-Za-z0-9_]{40,}',
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=]{40,}',
    rb'(?i:xclouddev/app-templates)',
]
regex = re.compile(b'|'.join(patterns))
findings = []
reviewed_public_fixtures = []
# These three upstream files contain public self-test/development keys or npm
# defaults. Accept only bytes identical to their pinned public source artifacts.
known_public = {}
base = Path('Dockerfile').read_text().splitlines()[0].split()[1]
subprocess.run(['docker', 'pull', base], check=True, stdout=subprocess.DEVNULL)
cid = subprocess.check_output(['docker', 'create', base], text=True).strip()
try:
    architecture = subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Architecture}}'], text=True).strip()
    triplet = {'amd64': 'x86_64', 'arm64': 'aarch64'}[architecture]
    for path in ['usr/local/lib/node_modules/npm/.npmrc', f'usr/lib/{triplet}-linux-gnu/libgnutls.so.30.34.3']:
        data = subprocess.check_output(['docker', 'cp', cid + ':/' + path, '-'])
        with tarfile.open(fileobj=io.BytesIO(data)) as copied:
            member = next(m for m in copied if m.isfile())
            known_public[path] = hashlib.sha256(copied.extractfile(member).read()).hexdigest()
finally:
    subprocess.run(['docker', 'rm', cid], check=True, stdout=subprocess.DEVNULL)
package = json.loads(Path('package-lock.json').read_text())['packages']['node_modules/miniflare']
assert package['resolved'].startswith('https://registry.npmjs.org/miniflare/')
with urllib.request.urlopen(package['resolved'], timeout=60) as response:
    data = response.read()
assert package['integrity'] == 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as npm:
    known_public['app/node_modules/miniflare/dist/src/index.js'] = hashlib.sha256(npm.extractfile('package/dist/src/index.js').read()).hexdigest()
files = 0
readmes = []
with tempfile.TemporaryDirectory(prefix='emdash-layer-audit-') as tmp:
    saved = Path(tmp) / 'image.tar'
    subprocess.run(['docker', 'save', '-o', str(saved), image], check=True)
    with tarfile.open(saved) as archive:
        manifest = json.load(archive.extractfile('manifest.json'))[0]
        config_bytes = archive.extractfile(manifest['Config']).read()
        config = json.loads(config_bytes)
        labels = config['config']['Labels']
        assert labels['org.opencontainers.image.source'] == 'https://github.com/neobuilds/emdash-container'
        assert labels['org.opencontainers.image.licenses'] == 'MIT'
        assert not regex.search(config_bytes), 'Unexpected private metadata or credential'
        assert all(not e.startswith('EMDASH_ENCRYPTION_KEY') for e in config['config']['Env'])
        for layer in manifest['Layers']:
            with tarfile.open(fileobj=archive.extractfile(layer), mode='r|*') as contents:
                for member in contents:
                    if not member.isfile():
                        continue
                    files += 1
                    path = member.name
                    sensitive_path = '/.git/' in '/' + path or path.endswith(('/.npmrc', '/.git-credentials', '/id_rsa', '/id_ed25519'))
                    f = contents.extractfile(member)
                    digest = hashlib.sha256()
                    previous = b''
                    matched = False
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        if regex.search(previous + chunk):
                            matched = True
                        previous = chunk[-512:]
                    if matched or sensitive_path:
                        if known_public.get(path) == digest.hexdigest():
                            reviewed_public_fixtures.append({'path': path, 'sha256': digest.hexdigest(), 'basis': 'byte-identical pinned public dependency'})
                        else:
                            findings.append({'path': path, 'reason': 'credential/private-reference pattern or sensitive filename'})
                    if path.lower().endswith('readme.md') and 'node_modules/' not in path:
                        readmes.append({'path': path, 'sha256': digest.hexdigest()})
        result = {'image': image, 'layers': len(manifest['Layers']), 'files_scanned': files, 'labels': labels, 'non_dependency_readmes': readmes, 'findings': findings, 'reviewed_public_fixtures': reviewed_public_fixtures, 'limitations': 'Heuristic scan; public upstream dependencies can contain test fixtures. Build inputs are separately allowlisted.'}
        Path(output).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        assert not findings, 'Public-content audit requires review'
