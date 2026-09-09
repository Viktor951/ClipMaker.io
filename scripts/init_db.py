import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', '.env'))

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/clipmaker_db")

async def init_db():
    print(f"Conectando ao banco de dados: {DB_URL}")
    conn = await asyncpg.connect(DB_URL)
    
    try:
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            passwordHash TEXT NOT NULL,
            name TEXT,
            credits INTEGER DEFAULT 60,
            createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            userId TEXT NOT NULL,
            title TEXT NOT NULL,
            sourceUrl TEXT,
            sourceFileKey TEXT NOT NULL,
            durationSec REAL NOT NULL,
            status TEXT DEFAULT 'PENDING',
            errorMessage TEXT,
            createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(userId) REFERENCES users(id) ON DELETE CASCADE
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS transcriptions (
            id TEXT PRIMARY KEY,
            projectId TEXT UNIQUE NOT NULL,
            fullText TEXT NOT NULL,
            language TEXT DEFAULT 'pt',
            wordsJson TEXT NOT NULL,
            createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
        )
        ''')

        await conn.execute('''
        CREATE TABLE IF NOT EXISTS clips (
            id TEXT PRIMARY KEY,
            projectId TEXT NOT NULL,
            title TEXT NOT NULL,
            hookReason TEXT NOT NULL,
            startTime REAL NOT NULL,
            endTime REAL NOT NULL,
            durationSec REAL NOT NULL,
            viralScore INTEGER NOT NULL,
            aspectRatio TEXT DEFAULT '9:16',
            renderedUrl TEXT,
            status TEXT DEFAULT 'QUEUED',
            errorMessage TEXT,
            captionConfig TEXT,
            createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
        )
        ''')

        print("Banco de dados PostgreSQL inicializado com sucesso!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(init_db())
