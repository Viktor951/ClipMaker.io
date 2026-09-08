import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dev.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        passwordHash TEXT NOT NULL,
        name TEXT,
        credits INTEGER DEFAULT 60,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        userId TEXT NOT NULL,
        title TEXT NOT NULL,
        sourceUrl TEXT,
        sourceFileKey TEXT NOT NULL,
        durationSec REAL NOT NULL,
        status TEXT DEFAULT 'PENDING',
        errorMessage TEXT,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(userId) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transcriptions (
        id TEXT PRIMARY KEY,
        projectId TEXT UNIQUE NOT NULL,
        fullText TEXT NOT NULL,
        language TEXT DEFAULT 'pt',
        wordsJson TEXT NOT NULL,
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    cursor.execute('''
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
        createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
    )
    ''')

    conn.commit()
    conn.close()
    print("Banco de dados SQLite inicializado com sucesso em", DB_PATH)

if __name__ == "__main__":
    init_db()
