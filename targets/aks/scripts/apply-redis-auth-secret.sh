#!/usr/bin/env sh
set -eu

if [ "${HALLIGALLI_OPERATION_APPROVED:-}" != "1" ]; then
  echo "Refusing to create a Redis credential without HALLIGALLI_OPERATION_APPROVED=1." >&2
  exit 1
fi

password="$(openssl rand -hex 32)"

kubectl -n halligalli create secret generic halligalli-redis-auth \
  --from-literal=username=halligalli-api \
  --from-literal=password="$password" \
  --dry-run=client -o yaml | kubectl apply -f -
