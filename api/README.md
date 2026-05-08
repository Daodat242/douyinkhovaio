# Self-host douyin.wtf API on Railway

Service riêng để bot gọi qua mạng internal Railway, bypass demo công cộng "fragile" của `api.douyin.wtf`.

## Deploy steps

### 1. Tạo service mới trên Railway

Trong cùng project Railway của bot:

- Click **+ New** → **GitHub Repo** → chọn repo này (`douyinkhovaio`)
- Service được tạo. Đổi tên thành ví dụ `douyin-api`.

### 2. Set Root Directory

Settings → Service → **Root Directory**: `api`

Railway sẽ thấy `api/Dockerfile` + `api/railway.json` và tự build.

### 3. Deploy

Tab Deployments → Build sẽ chạy ~3-5 phút (clone repo + pip install).

Khi xong, tab Logs sẽ thấy:
```
[entrypoint] Patched config.yaml: Host_IP=0.0.0.0 Host_Port=<PORT>
INFO:     Uvicorn running on http://0.0.0.0:<PORT>
INFO:     Application startup complete.
```

### 4. Trỏ bot service sang API mới

Sang service bot (service chính), Settings → Variables, thêm:

```
DOUYIN_WTF_ENDPOINT=http://${{douyin-api.RAILWAY_PRIVATE_DOMAIN}}:${{douyin-api.PORT}}
```

> Thay `douyin-api` bằng tên service API mày đã đặt ở step 1.

Railway sẽ tự expand reference này tại runtime → bot gọi API qua mạng nội bộ Railway (không qua public Internet, không tốn bandwidth).

Redeploy bot service để pick up env var mới.

### 5. Verify

Test gửi link Douyin cho bot. Logs bot sẽ thấy:
```
Provider=douyin.wtf thành công (URL=..., video_id=...)
```

## Pin commit (optional)

Mặc định Dockerfile pull `main` của repo Evil0ctal mỗi lần build. Để pin về 1 commit cụ thể (tránh upstream breaking), set Railway build arg:

```
REPO_REF=v4.1.2
```

(Settings → Build → Build args)

## Public access (optional)

Mặc định service API chỉ accessible internal. Nếu muốn test từ browser/curl, Settings → Networking → **Generate Domain**. Truy cập `https://<your-api>.up.railway.app/docs` để xem Swagger UI.

⚠️ Nếu enable public domain, nhớ set rate limit hoặc auth nếu không muốn ai cũng xài API miễn phí của mày.

## Troubleshooting

**Build fail "git clone"**: Repo Evil0ctal có thể bị move/rename. Check link trong Dockerfile.

**Runtime fail "config.yaml not found"**: Repo structure đổi. Patch entrypoint.sh path.

**Bot vẫn fail với "douyin.wtf: ..."**: Check API logs xem có request đến không. Nếu có mà fail, có thể cần config cookie cho Douyin trong `config.yaml` (Evil0ctal khuyến nghị).
