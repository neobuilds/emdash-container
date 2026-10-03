"""Scan every saved image layer, including deleted files, before publication.
Heuristic credential detection is not a guarantee that arbitrary secrets are absent.
"""
import hashlib
import json
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
                    if '/.git/' in '/' + path or path.endswith(('/.npmrc', '/.git-credentials', '/id_rsa', '/id_ed25519')):
                        findings.append({'path': path, 'reason': 'sensitive filename'})
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
                    if matched:
                        findings.append({'path': path, 'reason': 'credential or private-repository pattern'})
                    if path.lower().endswith('readme.md') and 'node_modules/' not in path:
                        readmes.append({'path': path, 'sha256': digest.hexdigest()})
        result = {'image': image, 'layers': len(manifest['Layers']), 'files_scanned': files, 'labels': labels, 'non_dependency_readmes': readmes, 'findings': findings, 'limitations': 'Heuristic scan; public upstream dependencies can contain test fixtures. Build inputs are separately allowlisted.'}
        Path(output).write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        assert not findings, 'Public-content audit requires review'
