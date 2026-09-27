#!/usr/bin/env sh
set -eu

secret() { openssl rand -hex 32; }

cat <<EOF
# Copy these values into the two local .env files. Do not save this output in Git.
POSTGRES_PASSWORD=$(secret)
DB_PASSWORD=$(secret)
MINIO_ACCESS_KEY=vexa-$(openssl rand -hex 8)
MINIO_SECRET_KEY=$(secret)
ADMIN_TOKEN=$(secret)
INTERNAL_API_SECRET=$(secret)
VEXA_WEBHOOK_SECRET=$(secret)
EOF

