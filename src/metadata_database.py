import duckdb
import streamlit as st
import traceback
from datetime import datetime
import os

class MetadataDatabase:
    """Handles conversation and message persistence in DuckDB."""
    
    def __init__(self, db_path: str = None):
        """Initialize with a DuckDB connection.
        
        Args:
            db_path: Path to DuckDB file. If None, uses session state connection.
        """
        if db_path:
            try:
                self.conn = duckdb.connect(db_path)
            except duckdb.BinderException as e:
                # Check if it's a WAL replay error
                if "Failure while replaying WAL" in str(e):
                    print(f"WARNING - WAL replay error: {e}. Attempting to recover by removing the WAL file.")
                    wal_path = db_path + ".wal"
                    if os.path.exists(wal_path):
                        try:
                            os.remove(wal_path)
                            print(f"INFO - Removed potentially corrupt WAL file: {wal_path}")
                            # Try connecting again after removing the WAL
                            self.conn = duckdb.connect(db_path)
                            print("INFO - Successfully reconnected to database.")
                        except Exception as recovery_e:
                            print(f"ERROR - Failed to remove WAL file and recover. Please check permissions or manually delete the file. Error: {recovery_e}")
                            raise e
                    else:
                        print("ERROR - WAL file not found for removal, cannot recover.")
                        raise e
                else:
                    # Reraise other binder exceptions
                    raise e
        else:
            self.conn = st.session_state.get("conn")
            if not self.conn:
                raise ValueError("No DuckDB connection available in session state and no db_path provided")
    
    def initialize_schema(self):
        """Initialize pet_meta schema and tables if they don't exist"""
        print("DEBUG - Initializing pet_meta schema")
        try:
            # Create schema if it doesn't exist
            self.conn.execute("CREATE SCHEMA IF NOT EXISTS pet_meta")
            
            # Create sequences
            self.conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.conversation_seq
                START 1 INCREMENT 1
            """)
            
            self.conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.message_log_seq
                START 1 INCREMENT 1
            """)
            
            # Create conversations table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS pet_meta.conversations (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_flagged_for_training BOOLEAN DEFAULT FALSE,
                    is_archived BOOLEAN DEFAULT FALSE,
                    notes TEXT
                )
            """)
            
            # Create message_log table with conversation_id foreign key
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS pet_meta.message_log (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    role VARCHAR,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    feedback_score INTEGER DEFAULT 0,
                    FOREIGN KEY (conversation_id) REFERENCES pet_meta.conversations(id)
                )
            """)
            self.conn.execute("ALTER TABLE pet_meta.message_log ADD COLUMN IF NOT EXISTS feedback_score INTEGER DEFAULT 0")
            
        except Exception as e:
            error_msg = f"Failed to initialize pet_meta schema: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Schema initialization traceback: {traceback.format_exc()}")
            # Don't re-raise, as we want the app to continue even if metadata tables can't be created
    
    def create_conversation(self, title: str) -> int:
        """Create a new conversation and return its ID"""
        try:
            result = self.conn.execute("""
                INSERT INTO pet_meta.conversations (id, title)
                VALUES (nextval('pet_meta.conversation_seq'), ?)
                RETURNING id
            """, [title]).fetchone()
            
            if result:
                conversation_id = result[0]  # Already a Python int
                # Commit to ensure data is persisted to disk
                self.conn.commit()
                print(f"DEBUG - Created new conversation with ID: {conversation_id}")
                return conversation_id
            else:
                print("ERROR - Failed to create conversation: no ID returned")
                return None
        except Exception as e:
            print(f"ERROR - Failed to create conversation: {str(e)}")
            print(f"ERROR - Conversation creation traceback: {traceback.format_exc()}")
            return None

    def update_conversation(self, conversation_id: int, title: str = None, is_flagged: bool = None, 
                          is_archived: bool = None, notes: str = None) -> bool:
        """Update conversation metadata"""
        try:
            updates = []
            params = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if is_flagged is not None:
                updates.append("is_flagged_for_training = ?")
                params.append(is_flagged)
            if is_archived is not None:
                updates.append("is_archived = ?")
                params.append(is_archived)
            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)
            
            if not updates:
                return True  # Nothing to update
                
            updates.append("last_updated = CURRENT_TIMESTAMP")
            params.append(conversation_id)
            
            query = f"""
                UPDATE pet_meta.conversations 
                SET {', '.join(updates)}
                WHERE id = ?
            """
            
            self.conn.execute(query, params)
            # Commit to ensure data is persisted to disk
            self.conn.commit()
            print(f"DEBUG - Updated conversation {conversation_id}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to update conversation: {str(e)}")
            print(f"ERROR - Conversation update traceback: {traceback.format_exc()}")
            return False

    def get_conversations(self, include_archived: bool = False) -> list[dict]:
        """Get list of all conversations"""
        try:
            query = """
                SELECT id, title, created_at, last_updated, 
                       is_flagged_for_training, is_archived, notes
                FROM pet_meta.conversations
            """
            if not include_archived:
                query += " WHERE NOT is_archived"
            query += " ORDER BY last_updated DESC"
            
            results = self.conn.execute(query).fetchall()
            conversations = []
            for row in results:
                conversations.append({
                    'id': row[0],
                    'title': row[1],
                    'created_at': row[2],
                    'last_updated': row[3],
                    'is_flagged_for_training': row[4],
                    'is_archived': row[5],
                    'notes': row[6]
                })
            return conversations
        except Exception as e:
            print(f"ERROR - Failed to get conversations: {str(e)}")
            print(f"ERROR - Get conversations traceback: {traceback.format_exc()}")
            return []

    def log_message(self, message: dict, conversation_id: int) -> int | None:
        """Store a message in the pet_meta.message_log table and return its ID."""
        try:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            
            # Insert the message into the log and return the new ID
            result = self.conn.execute("""
                INSERT INTO pet_meta.message_log (id, conversation_id, role, content)
                VALUES (nextval('pet_meta.message_log_seq'), ?, ?, ?)
                RETURNING id
            """, [conversation_id, role, content]).fetchone()
            
            if not result:
                print(f"ERROR - Message logging failed for conversation {conversation_id}, no ID returned")
                return None

            new_id = result[0]

            # Update conversation last_updated timestamp
            self.conn.execute("""
                UPDATE pet_meta.conversations
                SET last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [conversation_id])
            
            # Commit to ensure data is persisted to disk
            self.conn.commit()
            
            print(f"DEBUG - Message logged to conversation {conversation_id} with new ID {new_id}")
            return new_id
        except Exception as e:
            error_msg = f"Failed to log message: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message logging traceback: {traceback.format_exc()}")
            return None
    
    def load_messages(self, conversation_id: int) -> list[dict]:
        """Load messages for a specific conversation, including their IDs."""
        try:
            results = self.conn.execute("""
                SELECT id, role, content, feedback_score
                FROM pet_meta.message_log
                WHERE conversation_id = ?
                ORDER BY id ASC
            """, [conversation_id]).fetchall()
            
            if not results:
                print(f"DEBUG - No messages found for conversation {conversation_id}")
                return []
            
            messages = []
            for row in results:
                messages.append({
                    "id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "feedback_score": row[3],
                })
            
            print(f"DEBUG - Loaded {len(messages)} messages from conversation {conversation_id}")
            return messages
        except Exception as e:
            error_msg = f"Failed to load messages: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message loading traceback: {traceback.format_exc()}")
            return []

    def update_message_content(self, message_id: int, content: str) -> bool:
        """Updates the content of a specific message."""
        try:
            res = self.conn.execute("SELECT id, conversation_id FROM pet_meta.message_log WHERE id = ?", [message_id]).fetchone()
            if not res:
                print(f"ERROR - No message found with id {message_id} to update.")
                return False
            
            conversation_id = res[1]

            self.conn.execute("UPDATE pet_meta.message_log SET content = ? WHERE id = ?", [content, message_id])
            
            self.conn.execute("UPDATE pet_meta.conversations SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", [conversation_id])
            
            # Commit to ensure data is persisted to disk
            self.conn.commit()
            
            print(f"DEBUG - Updated content for message {message_id} in conversation {conversation_id}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to update message content for id {message_id}: {e}")
            print(traceback.format_exc())
            return False

    def update_feedback_score(self, message_id: int, score: int) -> bool:
        """Updates the feedback score of a specific message."""
        try:
            self.conn.execute("UPDATE pet_meta.message_log SET feedback_score = ? WHERE id = ?", [score, message_id])
            # Commit to ensure data is persisted to disk
            self.conn.commit()
            print(f"DEBUG - Updated feedback score for message {message_id} to {score}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to update feedback score for id {message_id}: {e}")
            print(traceback.format_exc())
            return False

    def get_feedback_score(self, message_id: int) -> int:
        """Gets the feedback score of a specific message."""
        try:
            result = self.conn.execute("SELECT feedback_score FROM pet_meta.message_log WHERE id = ?", [message_id]).fetchone()
            if result:
                return result[0] or 0
            return 0
        except Exception as e:
            print(f"ERROR - Failed to get feedback score for id {message_id}: {e}")
            return 0

    def delete_subsequent_messages(self, conversation_id: int, message_id: int) -> bool:
        """Deletes all messages after a specific message ID in a conversation."""
        try:
            self.conn.execute("""
                DELETE FROM pet_meta.message_log
                WHERE conversation_id = ? AND id > ?
            """, [conversation_id, message_id])
            
            self.conn.execute("UPDATE pet_meta.conversations SET last_updated = CURRENT_TIMESTAMP WHERE id = ?", [conversation_id])
            
            # Commit to ensure data is persisted to disk
            self.conn.commit()

            print(f"DEBUG - Deleted messages after {message_id} in conversation {conversation_id}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to delete subsequent messages for conversation {conversation_id}: {e}")
            print(traceback.format_exc())
            return False

    def trim_conversation_after_message(self, conversation_id: int, message_id: int) -> bool:
        """Delete all messages after the specified message ID in a conversation"""
        try:
            # Delete messages after the given message_id
            self.conn.execute("""
                DELETE FROM pet_meta.message_log
                WHERE conversation_id = ?
                AND id >= ?
            """, [conversation_id, message_id])
            
            # Update conversation last_updated timestamp
            self.conn.execute("""
                UPDATE pet_meta.conversations
                SET last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [conversation_id])
            
            # Commit to ensure data is persisted to disk
            self.conn.commit()
            
            print(f"DEBUG - Trimmed conversation {conversation_id} after message {message_id}")
            return True
        except Exception as e:
            error_msg = f"Failed to trim conversation: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Conversation trim traceback: {traceback.format_exc()}")
            return False

    def commit(self) -> bool:
        """Explicitly commit any pending transactions. Useful for periodic commits during idle times."""
        try:
            self.conn.commit()
            print("DEBUG - Explicitly committed metadata database transactions")
            return True
        except Exception as e:
            print(f"ERROR - Failed to commit metadata database: {e}")
            return False

    def checkpoint(self) -> bool:
        """Perform a WAL checkpoint to merge WAL file back into main database file."""
        try:
            self.conn.execute("PRAGMA force_checkpoint")
            print("DEBUG - WAL checkpoint completed, WAL file should be smaller")
            return True
        except Exception as e:
            print(f"ERROR - Failed to checkpoint WAL: {e}")
            return False

    def commit_and_checkpoint(self) -> bool:
        """Commit and checkpoint in one operation for maximum data persistence."""
        try:
            self.conn.commit()
            self.conn.execute("PRAGMA force_checkpoint") 
            print("DEBUG - Committed and checkpointed metadata database")
            return True
        except Exception as e:
            print(f"ERROR - Failed to commit and checkpoint: {e}")
            return False 