-- Migração 007 — Suporte a status EXPIRED em clipes/projetos e flag de estorno de créditos
-- Idempotente, sem DROP

-- 1. Garante coluna credits_refunded em projects para estorno idempotente
ALTER TABLE projects ADD COLUMN IF NOT EXISTS credits_refunded BOOLEAN DEFAULT FALSE;

-- 2. Índices para acelerar consultas por status e projetos expirados
CREATE INDEX IF NOT EXISTS idx_clips_status ON clips (status);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects (status);
