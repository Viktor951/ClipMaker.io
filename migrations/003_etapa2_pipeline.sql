-- Migração 003 — Etapa 2: enquadramento persistente, fallback de IA e reuso de transcrições (idempotente)

-- 1. Enquadramento facial persistente por clipe
ALTER TABLE clips ADD COLUMN IF NOT EXISTS face_center_x INT;

-- 2. Registro de acionamento de fallback matemático no projeto
ALTER TABLE projects ADD COLUMN IF NOT EXISTS ai_cuts_fallback BOOLEAN DEFAULT FALSE;

-- 3. Campos para reuso de transcrição
ALTER TABLE transcriptions ADD COLUMN IF NOT EXISTS userId UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE transcriptions ADD COLUMN IF NOT EXISTS sourceUrl VARCHAR;
ALTER TABLE transcriptions ADD COLUMN IF NOT EXISTS fileHash VARCHAR;

CREATE INDEX IF NOT EXISTS idx_transcriptions_lookup ON transcriptions(userId, sourceUrl, fileHash);
