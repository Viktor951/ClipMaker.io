-- Migração 005 — Etapa 4: Garantir persistência de miniatura do clipe (idempotente)
ALTER TABLE clips ADD COLUMN IF NOT EXISTS thumbnail_key VARCHAR;
CREATE INDEX IF NOT EXISTS idx_clips_thumbnail ON clips (thumbnail_key);
