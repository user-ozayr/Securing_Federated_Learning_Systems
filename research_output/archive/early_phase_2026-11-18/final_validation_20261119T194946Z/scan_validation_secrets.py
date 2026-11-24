import re
from pathlib import Path
root=Path('/home/ubuntu/gemini/fl-security-research-spdz2k-thesis')
patterns=[('private_key_header',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
('literal_credential_assignment',re.compile(r'''(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|secret|control[_-]?token)\b\s*[:=]\s*['\"][^'\"]{16,}['\"]'''))]
for label,pattern in patterns:
    hits=[]
    for base in ('src','configs'):
        for p in (root/base).rglob('*'):
            if p.is_file() and p.suffix in ('.py','.yaml','.yml','.toml','.json','.mpc'):
                try: lines=p.read_text(errors='ignore').splitlines()
                except OSError: continue
                hits.extend(f'{p.relative_to(root)}:{i}' for i,line in enumerate(lines,1) if pattern.search(line))
    print(f'{label}: {len(hits)} match(es)')
    for h in hits[:50]: print('  '+h)
