import os
from db_helper import DBHelper

def migrate_db():
    print("Starting database migration...")
    db = DBHelper()
    conn = db.get_connection()
    
    if not conn:
        print("Failed to connect to database.")
        return

    try:
        cursor = conn.cursor()
        print("Altering table messages_sign_chat...")
        # Change message_content from VARCHAR to TEXT to support large JSON strings
        cursor.execute("ALTER TABLE messages_sign_chat MODIFY COLUMN message_content TEXT")
        conn.commit()
        print("Migration successful: message_content column changed to TEXT.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == "__main__":
    migrate_db()
