-- Migração 002 — Adiciona coluna thumbnail_key na tabela clips (idempotente)
ALTER TABLE clips ADD COLUMN IF NOT EXISTS thumbnail_key VARCHAR;
