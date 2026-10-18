-- Migração 006 — Etapa B: Robustez de jobs e watchdog de projetos travados
-- Idempotente, sem DROP

-- 1. Garante a coluna updatedAt em projects com valor padrão CURRENT_TIMESTAMP
ALTER TABLE projects ADD COLUMN IF NOT EXISTS updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 2. Índice composto para agilizar o watchdog de projetos travados por status e data de atualização
CREATE INDEX IF NOT EXISTS idx_projects_status_updated ON projects (status, updatedAt);
