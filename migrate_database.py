"""
Database Migration Script for VTM Storyteller
Ensures all required columns exist in the characters table
"""

import sqlite3

# Columns used by custom character creation, Demiplane links, PDF upload, and sheet views.
CHARACTER_COLUMNS = {
    'name': 'TEXT',
    'user_id': 'TEXT',
    'chronicle_id': 'INTEGER',
    'clan': 'TEXT',
    'concept': 'TEXT',
    'predator_type': 'TEXT',
    'generation': 'INTEGER DEFAULT 13',
    'sire': 'TEXT',
    'ambition': 'TEXT',
    'desire': 'TEXT',
    'attributes': 'TEXT',
    'skills': 'TEXT',
    'disciplines': 'TEXT',
    'backgrounds': 'TEXT',
    'health': 'INTEGER DEFAULT 3',
    'willpower': 'INTEGER DEFAULT 2',
    'health_max': 'INTEGER DEFAULT 3',
    'willpower_max': 'INTEGER DEFAULT 3',
    'humanity': 'INTEGER DEFAULT 7',
    'hunger': 'INTEGER DEFAULT 1',
    'resonance': 'TEXT',
    'blood_potency': 'INTEGER DEFAULT 0',
    'experience': 'INTEGER DEFAULT 0',
    'total_experience': 'INTEGER DEFAULT 0',
    'blood_surge': 'TEXT',
    'power_bonus': 'TEXT',
    'mend_amount': 'TEXT',
    'rouse_reroll': 'TEXT',
    'bane_severity': 'TEXT',
    'clan_bane': 'TEXT',
    'clan_compulsion': 'TEXT',
    'sect': 'TEXT',
    'rank_title': 'TEXT',
    'pdf_path': 'TEXT',
    'pdf_upload_date': 'TIMESTAMP',
    'pdf_hash': 'TEXT',
    'portrait_path': 'TEXT',
    'demiplane_url': 'TEXT',
    'roll20_character_id': 'TEXT',
    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
    'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
}

CHARACTERS_CREATE_SQL = '''
    CREATE TABLE characters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        name TEXT NOT NULL,
        concept TEXT,
        chronicle_id INTEGER,
        clan TEXT,
        predator_type TEXT,
        generation INTEGER DEFAULT 13,
        sire TEXT,
        ambition TEXT,
        desire TEXT,
        attributes TEXT,
        skills TEXT,
        disciplines TEXT,
        backgrounds TEXT,
        health INTEGER DEFAULT 3,
        willpower INTEGER DEFAULT 2,
        health_max INTEGER DEFAULT 3,
        willpower_max INTEGER DEFAULT 3,
        humanity INTEGER DEFAULT 7,
        hunger INTEGER DEFAULT 1,
        resonance TEXT,
        blood_potency INTEGER DEFAULT 0,
        experience INTEGER DEFAULT 0,
        total_experience INTEGER DEFAULT 0,
        blood_surge TEXT,
        power_bonus TEXT,
        mend_amount TEXT,
        rouse_reroll TEXT,
        bane_severity TEXT,
        clan_bane TEXT,
        clan_compulsion TEXT,
        sect TEXT,
        rank_title TEXT,
        pdf_path TEXT,
        pdf_upload_date TIMESTAMP,
        pdf_hash TEXT,
        portrait_path TEXT,
        demiplane_url TEXT,
        roll20_character_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''


def ensure_character_columns(conn):
    """Add any missing characters-table columns on an existing connection."""
    c = conn.cursor()
    c.execute("PRAGMA table_info(characters)")
    existing_columns = {row[1] for row in c.fetchall()}
    added_count = 0
    for column_name, column_type in CHARACTER_COLUMNS.items():
        if column_name not in existing_columns:
            try:
                c.execute(f"ALTER TABLE characters ADD COLUMN {column_name} {column_type}")
                added_count += 1
                print(f"Added column: {column_name} ({column_type})")
            except sqlite3.OperationalError as e:
                print(f"Failed to add column {column_name}: {e}")
    if added_count:
        conn.commit()
    return added_count


def migrate_database(db_path='vtm_storyteller.db'):
    """Migrate database to support PDF uploads and custom character creation."""

    print(f"Starting database migration for: {db_path}")

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='characters'")
    table_exists = c.fetchone() is not None

    if not table_exists:
        print("Characters table does not exist. Creating it now...")
        c.execute(CHARACTERS_CREATE_SQL)
        conn.commit()
        print("Characters table created successfully")
        conn.close()
        return

    c.execute("PRAGMA table_info(characters)")
    existing_columns = {row[1] for row in c.fetchall()}
    print(f"Existing columns: {existing_columns}")

    added_count = ensure_character_columns(conn)

    if added_count == 0:
        print("All required columns already exist")
    else:
        print(f"Added {added_count} new columns")

    c.execute("PRAGMA table_info(characters)")
    final_columns = {row[1] for row in c.fetchall()}
    print(f"Final column count: {len(final_columns)}")

    conn.close()
    print("Database migration completed successfully")


if __name__ == '__main__':
    migrate_database()
