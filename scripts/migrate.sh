#!/bin/sh
# Aplica migrations/*.sql em ordem, uma única vez cada (controle em schema_migrations).
# Roda a cada `docker compose up` como serviço one-shot.
set -eu

export PGPASSWORD="${POSTGRES_PASSWORD}"
PSQL="psql -h ${POSTGRES_HOST:-db} -U ${POSTGRES_USER} -d ${POSTGRES_DB} -v ON_ERROR_STOP=1 -q"

$PSQL -c "CREATE TABLE IF NOT EXISTS schema_migrations (
  filename TEXT PRIMARY KEY,
  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);"

for f in $(ls /migrations/*.sql | sort); do
  name=$(basename "$f")
  done_already=$($PSQL -tA -c "SELECT 1 FROM schema_migrations WHERE filename='${name}'")
  if [ "$done_already" = "1" ]; then
    echo "[migrate] já aplicada: ${name}"
    continue
  fi
  echo "[migrate] aplicando: ${name}"
  $PSQL --single-transaction -f "$f" -c "INSERT INTO schema_migrations(filename) VALUES ('${name}');"
done
echo "[migrate] concluído"
