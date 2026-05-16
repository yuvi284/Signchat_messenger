from flask import jsonify
import mysql.connector
from mysql.connector import Error, pooling
import os
import logging

# Configure logging for DB operations
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DBHelper:
    _connection_pool = None

    def __init__(self):
        if not DBHelper._connection_pool:
            try:
                DBHelper._connection_pool = mysql.connector.pooling.MySQLConnectionPool(
                    pool_name="mypool",
                    pool_size=5,
                    pool_reset_session=True,
                    host=os.environ.get('DB_HOST', 'db.dev.erp.mdi'),
                    user=os.environ.get('DB_USER', 'phpdev'),
                    password=os.environ.get('DB_PASSWORD', 'phpdev'),
                    database=os.environ.get('DB_NAME', 'phpdevs')
                )
                logger.info("Database connection pool created.")
            except Error as e:
                logger.error(f"Error creating connection pool: {e}")

    def get_connection(self):
        try:
            if DBHelper._connection_pool:
                return DBHelper._connection_pool.get_connection()
            else:
                logger.error("Connection pool is not initialized.")
                return None
        except Error as e:
            logger.error(f"Error getting connection from pool: {e}")
            return None

    def ensure_blocked_contacts_table(self, cursor):
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blocked_contacts_sign_chat (
                id INT AUTO_INCREMENT PRIMARY KEY,
                owner_mobile VARCHAR(20) NOT NULL,
                contact_mobile VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_blocked_contact (owner_mobile, contact_mobile)
            )
        """)

    def GetSavedContacts(self, owner_mobile):
        conn = self.get_connection()
        if conn is None:
            return {}

        try:
            cursor = conn.cursor()
            query = """
                SELECT c.contact_mobile, COALESCE(c.nickname, u.username) AS display_name
                FROM contacts_sign_chat c
                JOIN users_sign_chat u ON c.contact_mobile = u.mobile
                WHERE c.owner_mobile = %s
                AND u.is_active = 1
            """
            cursor.execute(query, (owner_mobile,))
            results = cursor.fetchall()

            contacts_dict = {row[0]: row[1] for row in results}  # mobile: display_name
            return contacts_dict

        except Exception as e:
            print(f"Error fetching saved contacts: {e}")
            return {}

        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def DeleteMessage(self, message_id):
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            query = "DELETE FROM messages_sign_chat WHERE id = %s"
            cursor.execute(query, (message_id,))
            conn.commit()
            return True

        except Exception as e:
            print(f"Error deleting message: {e}")
            return False

        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def StoreFeedback(self, message_id, feedback_text):
            conn = self.get_connection()
            if conn is None:
             return False
            try:
                cursor = conn.cursor()
                print(f"{message_id}  meassage id  and  {feedback_text} feedback  database")
                query = """
                    UPDATE messages_sign_chat
                    SET feedback = %s
                    WHERE id = %s
                """
                cursor.execute("UPDATE messages_sign_chat SET feedback = %s WHERE id = %s", (feedback_text, message_id))

                conn.commit()

                return {"success": True, "message": "Feedback submitted successfully!"}

            except Exception as e:
                print(f"Error storing feedback: {e}")
                return False

            finally:
                if cursor: cursor.close()
                if conn: conn.close()
    
    def GetSavedContacts1(self, owner_mobile):
        conn = self.get_connection()
        if conn is None:
            return []

        try:
            cursor = conn.cursor()
            self.ensure_blocked_contacts_table(cursor)
            query = """
                SELECT 
                    p.mobile,
                    c.nickname, 
                    u.username,
                    (
                        SELECT COUNT(*) 
                        FROM messages_sign_chat
                        WHERE CAST(sender_mobile AS CHAR) = CAST(p.mobile AS CHAR)
                        AND CAST(receiver_mobile AS CHAR) = %s
                        AND seen = 0
                    ) AS unread,
                    (
                        SELECT MAX(created_at)
                        FROM messages_sign_chat
                        WHERE (CAST(sender_mobile AS CHAR) = CAST(p.mobile AS CHAR) AND CAST(receiver_mobile AS CHAR) = %s)
                           OR (CAST(sender_mobile AS CHAR) = %s AND CAST(receiver_mobile AS CHAR) = CAST(p.mobile AS CHAR))
                    ) AS last_activity,
                    u.profile_picture,
                    c.contact_mobile IS NOT NULL AS is_saved,
                    b.contact_mobile IS NOT NULL AS is_blocked
                FROM (
                    SELECT contact_mobile AS mobile
                    FROM contacts_sign_chat
                    WHERE owner_mobile = %s

                    UNION

                    SELECT
                        CASE
                            WHEN CAST(sender_mobile AS CHAR) = %s THEN receiver_mobile
                            ELSE sender_mobile
                        END AS mobile
                    FROM messages_sign_chat
                    WHERE CAST(sender_mobile AS CHAR) = %s OR CAST(receiver_mobile AS CHAR) = %s

                    UNION

                    SELECT contact_mobile AS mobile
                    FROM blocked_contacts_sign_chat
                    WHERE owner_mobile = %s
                ) p
                JOIN users_sign_chat u ON p.mobile = u.mobile
                LEFT JOIN contacts_sign_chat c
                    ON CAST(c.owner_mobile AS CHAR) = %s AND CAST(c.contact_mobile AS CHAR) = CAST(p.mobile AS CHAR)
                LEFT JOIN blocked_contacts_sign_chat b
                    ON CAST(b.owner_mobile AS CHAR) = %s AND CAST(b.contact_mobile AS CHAR) = CAST(p.mobile AS CHAR)
                WHERE CAST(p.mobile AS CHAR) <> %s
                AND u.is_active = 1
                ORDER BY last_activity DESC, COALESCE(c.nickname, u.username) ASC
            """
            cursor.execute(query, (
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
                owner_mobile,
            ))
            results = cursor.fetchall()

            # row[0]=mobile, row[1]=nickname, row[2]=username, row[3]=unread,
            # row[4]=last_activity, row[5]=profile_picture, row[6]=is_saved,
            # row[7]=is_blocked
            return [{
                "mobile": row[0], 
                "nickname": row[1], 
                "name": row[2],
                "unread": row[3], 
                "last_activity": row[4], 
                "profile_picture": f"/static/uploads/{os.path.basename(row[5])}" if row[5] else None,
                "is_saved": bool(row[6]),
                "is_blocked": bool(row[7])
            } for row in results]

        except Exception as e:
            print(f"Error fetching saved contacts: {e}")
            return []

        finally:
            if cursor: cursor.close()
            if conn: conn.close()


    def SaveContact(self, owner_mobile, contact_mobile, nickname):
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            query = """
                INSERT IGNORE INTO contacts_sign_chat (owner_mobile, contact_mobile, nickname)
                VALUES (%s, %s, %s)
            """
            cursor.execute(query, (owner_mobile, contact_mobile, nickname))
            conn.commit()
            return True

        except Exception as e:
            print(f"Error saving contact: {e}")
            return False

        finally:
            if cursor: cursor.close()
            if conn: conn.close()


    def SaveChatMessage(self, sender_mobile, receiver_mobile, message_content, gesture_metadata_str):
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            # Fixed query to match placeholders
            query = """
                INSERT INTO messages_sign_chat  
                (sender_mobile, receiver_mobile, message_content, message_metadata, seen, status)
                VALUES (%s, %s, %s, %s, 0, 'sent')
            """
            cursor.execute(query, (sender_mobile, receiver_mobile, message_content, gesture_metadata_str))
            message_id = cursor.lastrowid
            conn.commit()
            return message_id

        except Exception as e:
            print(f"Error saving chat message: {e}")
            return False

        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def SearchContact(self, owner_mobile, search_keyword):
        conn = self.get_connection()
        if conn is None:
            return {"status": "error"}

        try:
            cursor = conn.cursor()
            like_search = f"{search_keyword}%"

            contact_list = []

            # Step 1: Search Saved Contacts (by name or number)
            cursor.execute("""
                SELECT nickname, contact_mobile FROM contacts_sign_chat 
                WHERE owner_mobile = %s AND (contact_mobile LIKE %s OR nickname LIKE %s)
            """, (owner_mobile, like_search, like_search))

            saved_contacts = cursor.fetchall()
            for contact in saved_contacts:
                contact_list.append({
                    "name": contact[0],
                    "mobile": contact[1],
                    "status": "saved"
                })

            # Step 2: Search Registered Users Not Already Saved (by number or name)
            cursor.execute("""
                SELECT username, mobile FROM users_sign_chat 
                WHERE is_active = 1 AND mobile !=%s AND
                    (mobile LIKE %s) AND 
                    mobile NOT IN (
                        SELECT contact_mobile FROM contacts_sign_chat WHERE owner_mobile = %s
                    )
            """, (owner_mobile, like_search,  owner_mobile))

            registered_users = cursor.fetchall()
            for user in registered_users:
                contact_list.append({
                    "name": user[0],
                    "mobile": user[1],
                    "status": "registered"
                })

            if contact_list:
                return {"status": "multiple", "contacts": contact_list}
            else:
                return {"status": "not_registered"}

        except Exception as e:
            print(f"Error searching contact: {e}")
            return {"status": "error"}
        finally:
            if cursor: cursor.close()
            if conn: conn.close()



    def GetChatMessages(self, user_mobile, contact_mobile):
        conn = self.get_connection()
        if conn is None:
            return []

        try:
            cursor = conn.cursor(dictionary=True)
            query = """
                SELECT 
                    id AS message_id,
                    sender_mobile, 
                    receiver_mobile, 
                    message_content, 
                    message_metadata,
                    seen,
                    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i') AS created_at
                FROM messages_sign_chat
                WHERE 
                    (sender_mobile = %s AND receiver_mobile = %s)
                    OR (sender_mobile = %s AND receiver_mobile = %s)
                ORDER BY created_at ASC
            """
            cursor.execute(query, (user_mobile, contact_mobile, contact_mobile, user_mobile))
            results = cursor.fetchall()
            return results

        except Exception as e:
            print(f"Error fetching chat messages: {e}")
            return []

        finally:
            if cursor: cursor.close()
            if conn: conn.close()



    def get_user_by_mobile(self, mobile):
        conn = self.get_connection()
        if conn is None:
            return None

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users_sign_chat WHERE mobile = %s", (mobile,))
            return cursor.fetchone()
        except Exception as e:
            print(f"Error fetching user by mobile: {e}")
            return None
        finally:
            if conn: conn.close()

    def get_user_by_email(self, email):
        conn = self.get_connection()
        if conn is None:
            return None

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users_sign_chat WHERE email = %s", (email,))
            return cursor.fetchone()
        except Exception as e:
            print(f"Error fetching user by email: {e}")
            return None
        finally:
            if conn: conn.close()

    def update_password_by_email(self, email, password_hash):
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            query = "UPDATE users_sign_chat SET password_hash = %s WHERE email = %s"
            cursor.execute(query, (password_hash, email))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating password: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

            
    def user_exists(self, mobile):
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users_sign_chat WHERE mobile = %s", (mobile,))
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error checking if user exists: {e}")
            return False
        finally:
            if conn: conn.close()


    def mark_messages_as_seen(self, sender_mobile, receiver_mobile):
        conn = self.get_connection()  
        if conn is None: return

        try:
            cursor = conn.cursor()
            sql = """
                UPDATE messages_sign_chat
                SET seen = 1
                WHERE CAST(sender_mobile AS CHAR) = %s
                AND CAST(receiver_mobile AS CHAR) = %s
                AND seen = 0
            """
            sender_mobile = str(sender_mobile or "").strip()
            receiver_mobile = str(receiver_mobile or "").strip()
            cursor.execute(sql, (sender_mobile, receiver_mobile))
            conn.commit()
        except Exception as e:
            print(f"Error marking messages as seen: {e}")
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def register_user(self, mobile, username, email, gender, password_hash, profile_picture):
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO users_sign_chat 
                (mobile, username, email, gender, password_hash, profile_picture)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (mobile, username, email, gender, password_hash, profile_picture))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error registering user: {e}")
            return False
        finally:
            if conn: conn.close()

    def get_profile_picture(self, mobile):
        conn = self.get_connection()
        if conn is None:
            return '/images/default_user.png'

        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT profile_picture FROM users_sign_chat WHERE mobile = %s"
            cursor.execute(query, (mobile,))
            row = cursor.fetchone()
            
            if row and row['profile_picture']:
                return row['profile_picture']
            else:
                return '/images/default_user.png'
            
        except Exception as e:
            print(f"Error fetching profile picture for {mobile}: {e}")
            return '/images/default_user.png'
        
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def update_contact_name(self, user_mobile, contact_mobile, new_name):
        conn = self.get_connection()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO contacts_sign_chat (owner_mobile, contact_mobile, nickname)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE nickname = VALUES(nickname)
            """
            cursor.execute(query, (user_mobile, contact_mobile, new_name))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating contact name: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()


        # Add new method to DBHelper class
    def update_user_profile(self, mobile, username, email, gender, profile_picture):
        conn = self.get_connection()
        if conn is None:
            return False

        try:
            cursor = conn.cursor()
            query = """
                UPDATE users_sign_chat 
                SET username = %s, 
                email = %s, 
                gender = %s, 
                profile_picture = %s
                WHERE mobile = %s
            """
            cursor.execute(query, (username, email, gender, profile_picture, mobile))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating user profile: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
            
    def delete_contact(self, user_mobile, contact_mobile):
        conn = self.get_connection()
        if not conn:
            return False
            
        try:
            cursor = conn.cursor()
            query = """
                DELETE FROM contacts_sign_chat
                WHERE owner_mobile = %s AND contact_mobile = %s
            """
            cursor.execute(query, (user_mobile, contact_mobile))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting contact: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def block_contact(self, user_mobile, contact_mobile):
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            self.ensure_blocked_contacts_table(cursor)
            query = """
                INSERT IGNORE INTO blocked_contacts_sign_chat (owner_mobile, contact_mobile)
                VALUES (%s, %s)
            """
            cursor.execute(query, (user_mobile, contact_mobile))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error blocking contact: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def unblock_contact(self, user_mobile, contact_mobile):
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            self.ensure_blocked_contacts_table(cursor)
            query = """
                DELETE FROM blocked_contacts_sign_chat
                WHERE owner_mobile = %s AND contact_mobile = %s
            """
            cursor.execute(query, (user_mobile, contact_mobile))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error unblocking contact: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def is_blocked_between(self, user_mobile, contact_mobile):
        conn = self.get_connection()
        if not conn:
            return False

        try:
            cursor = conn.cursor()
            self.ensure_blocked_contacts_table(cursor)
            query = """
                SELECT 1
                FROM blocked_contacts_sign_chat
                WHERE (owner_mobile = %s AND contact_mobile = %s)
                   OR (owner_mobile = %s AND contact_mobile = %s)
                LIMIT 1
            """
            cursor.execute(query, (user_mobile, contact_mobile, contact_mobile, user_mobile))
            return cursor.fetchone() is not None
        except Exception as e:
            print(f"Error checking blocked contact: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()

    def delete_contact_messages(self, user_mobile, contact_mobile):
        conn = self.get_connection()
        if not conn:
            return False
            
        try:
            cursor = conn.cursor()
            query = """
                DELETE FROM messages_sign_chat
                WHERE (sender_mobile = %s AND receiver_mobile = %s)
                   OR (sender_mobile = %s AND receiver_mobile = %s)
            """
            cursor.execute(query, (user_mobile, contact_mobile, contact_mobile, user_mobile))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting messages: {e}")
            return False
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    def GetMessageById(self, message_id):
        conn = self.get_connection()
        if conn is None:
            return None

        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT * FROM messages_sign_chat WHERE id = %s"
            cursor.execute(query, (message_id,))
            return cursor.fetchone()

        except Exception as e:
            print(f"Error fetching message by ID: {e}")
            return None

        finally:
            if cursor: cursor.close()
            if conn: conn.close()
