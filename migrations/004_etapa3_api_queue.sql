-- Migração 004: Fila, métricas de tempo e índices de concorrência
-- Idempotente, sem DROP

-- 1. Índices para agilizar contagem de concorrência por usuário e posição na fila
CREATE INDEX IF NOT EXISTS idx_projects_user_status ON projects (userId, status);
CREATE INDEX IF NOT EXISTS idx_projects_status_created ON projects (status, createdAt);

-- 2. Tabela de métricas para cálculo da média móvel de tempo por minuto de vídeo
CREATE TABLE IF NOT EXISTS job_metrics (
    id VARCHAR(36) PRIMARY KEY,
    projectId UUID REFERENCES projects(id) ON DELETE SET NULL,
    videoDurationSec REAL NOT NULL,
    totalProcessingSec REAL NOT NULL,
    secPerMinute REAL NOT NULL,
    createdAt TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_metrics_created_at ON job_metrics (createdAt DESC);
