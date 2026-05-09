#!/bin/sh
# Production entrypoint cho douyin.wtf API service.
#
# Quan trọng:
# 1. Bind tới '::' (IPv6) — Railway private networking là IPv6, bind 0.0.0.0
#    sẽ làm service không reachable từ services khác cùng project.
# 2. Bypass start.py của repo (chứa reload=True, hợp dev không hợp prod).
#    Gọi uvicorn module trực tiếp với args đúng cho production.
# 3. Vẫn patch config.yaml vì app.main có thể đọc Host_IP/Host_Port ở
#    module-level lúc import (tránh việc import fail).
set -e

PORT="${PORT:-8000}"

python3 - <<PYEOF
import os, yaml
port = int(os.environ.get('PORT', '8000'))
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
cfg.setdefault('API', {})
cfg['API']['Host_IP'] = '::'
cfg['API']['Host_Port'] = port
with open('config.yaml', 'w') as f:
    yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
print(f'[entrypoint] Patched config.yaml: Host_IP=::, Host_Port={port}')
PYEOF

# uvicorn binds to '::' = IPv6 all-interfaces, dual-stack mode trên Linux
# nhận cả IPv4 traffic. Cần thiết cho Railway internal networking.
exec python3 -m uvicorn app.main:app \
    --host '::' \
    --port "${PORT}" \
    --log-level info \
    --no-access-log
