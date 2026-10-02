"""Precache this build's app code, styles and local fonts for offline reopening."""
from pathlib import Path
import json
root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
assets = sorted(p.relative_to(dist).as_posix() for p in (dist / '_app' / 'immutable').rglob('*') if p.is_file() and p.suffix in {'.js', '.css', '.woff2', '.png', '.webp'})
assets += ['icons/icon-180.png', 'icons/icon-192.png', 'icons/icon-512.png', 'favicon.ico']
worker = dist / 'sw.js'
text = worker.read_text(encoding='utf-8')
assert 'const PRECACHE_ASSETS = [];' in text
worker.write_text(text.replace('const PRECACHE_ASSETS = [];', 'const PRECACHE_ASSETS = ' + json.dumps(assets) + ';'), encoding='utf-8')
print(f'Offline app assets: {len(assets)} files')
