# Self-hosted douyin.wtf API service for Railway.
#
# Build: clones Evil0ctal/Douyin_TikTok_Download_API at a pinned ref,
# installs deps, copies entrypoint that binds to Railway's $PORT.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Pin to main, override REPO_REF at build time to lock to a commit.
ARG REPO_REF=main
RUN git clone --depth 1 --branch ${REPO_REF} \
    https://github.com/Evil0ctal/Douyin_TikTok_Download_API.git . \
    && rm -rf .git

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir pyyaml

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
