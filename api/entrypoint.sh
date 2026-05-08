#!/bin/sh
# Bind douyin.wtf API to Railway's dynamic $PORT.
#
# Repo's start.py reads Host_IP/Host_Port from config.yaml. Railway sets
# PORT at runtime → patch config trước khi start uvicorn.
set -e

PORT="${PORT:-8000}"

python3 - <<PYEOF
import os, yaml
port = int(os.environ.get('PORT', '8000'))
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg.setdefault('API', {})
cfg['API']['Host_IP'] = '0.0.0.0'
cfg['API']['Host_Port'] = port
with open('config.yaml', 'w') as f:
    yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
print(f'[entrypoint] Patched config.yaml: Host_IP=0.0.0.0 Host_Port={port}')
PYEOF

exec python3 start.py
