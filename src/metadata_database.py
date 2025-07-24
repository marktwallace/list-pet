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
                
                # Set DuckDB to use UTC timezone to avoid server timezone issues
                try:
                    self.conn.execute("SET TimeZone = 'UTC'")
                    print("DEBUG - Metadata database timezone set to UTC")
                except Exception as tz_error:
                    print(f"WARNING - Failed to set metadata database timezone to UTC: {tz_error}")
                    
            except (duckdb.BinderException, duckdb.OperationalError) as e:
                # Check if it's a WAL replay error
                if "Failure while replaying WAL" in str(e):
                    print(f"FATAL - DuckDB WAL file is corrupt or unreplayable: {e}")
                    print(f"FATAL - This usually means the application did not shut down cleanly.")
                    print("FATAL - To prevent data loss, the application will not automatically delete the WAL file and will now exit.")
                    print(f"FATAL - Please inspect the database file '{db_path}' and its WAL file '{db_path}.wal'.")
                    print("FATAL - You may need to restore from a backup or manually move/delete the WAL file to start the application again.")
                    # Re-raise to stop the application
                    raise e
                else:
                    # Reraise other binder/operational exceptions
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
            
            self.conn.execute("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.feedback_details_seq
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
            
            # Create feedback_details table for detailed thumbs up/down feedback
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS pet_meta.feedback_details (
                    id INTEGER PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    feedback_type VARCHAR NOT NULL, -- 'thumbs_up' or 'thumbs_down'
                    
                    -- Thumbs Up fields
                    remember_uprate BOOLEAN,
                    description_text TEXT,
                    
                    -- Thumbs Down fields  
                    what_was_wrong TEXT,
                    what_user_wanted TEXT,
                    
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES pet_meta.message_log(id)
                )
            """)
            
            # Commit and checkpoint to ensure schema is durably persisted
            self.conn.commit()
            self.conn.execute("PRAGMA force_checkpoint")
            print("DEBUG - pet_meta schema initialized and checkpointed.")

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
            # A standard CHECKPOINT will fail if transactions are active, which is safe.
            # It should only be called when the application is idle.
            self.conn.execute("CHECKPOINT")
            print("DEBUG - Manual WAL checkpoint completed.")
            return True
        except Exception as e:
            print(f"ERROR - Failed to perform manual WAL checkpoint: {e}")
            return False 

    def save_feedback_details(self, message_id: int, feedback_type: str, 
                             remember_uprate: bool = None, description_text: str = None,
                             what_was_wrong: str = None, what_user_wanted: str = None) -> bool:
        """Save or update detailed feedback for a message."""
        try:
            # Check if feedback already exists for this message and type
            result = self.conn.execute("""
                SELECT id FROM pet_meta.feedback_details 
                WHERE message_id = ? AND feedback_type = ?
            """, [message_id, feedback_type]).fetchone()
            
            if result:
                # Update existing feedback
                feedback_id = result[0]
                updates = []
                params = []
                
                if remember_uprate is not None:
                    updates.append("remember_uprate = ?")
                    params.append(remember_uprate)
                if description_text is not None:
                    updates.append("description_text = ?")
                    params.append(description_text)
                if what_was_wrong is not None:
                    updates.append("what_was_wrong = ?")
                    params.append(what_was_wrong)
                if what_user_wanted is not None:
                    updates.append("what_user_wanted = ?")
                    params.append(what_user_wanted)
                
                if updates:
                    updates.append("updated_at = CURRENT_TIMESTAMP")
                    params.append(feedback_id)
                    
                    query = f"""
                        UPDATE pet_meta.feedback_details 
                        SET {', '.join(updates)}
                        WHERE id = ?
                    """
                    self.conn.execute(query, params)
            else:
                # Insert new feedback
                self.conn.execute("""
                    INSERT INTO pet_meta.feedback_details 
                    (id, message_id, feedback_type, remember_uprate, description_text, 
                     what_was_wrong, what_user_wanted)
                    VALUES (nextval('pet_meta.feedback_details_seq'), ?, ?, ?, ?, ?, ?)
                """, [message_id, feedback_type, remember_uprate, description_text, 
                      what_was_wrong, what_user_wanted])
            
            self.conn.commit()
            print(f"DEBUG - Saved feedback details for message {message_id}, type {feedback_type}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to save feedback details: {e}")
            print(traceback.format_exc())
            return False

    def get_feedback_details(self, message_id: int, feedback_type: str) -> dict | None:
        """Get detailed feedback for a message and feedback type."""
        try:
            result = self.conn.execute("""
                SELECT remember_uprate, description_text, what_was_wrong, what_user_wanted,
                       created_at, updated_at
                FROM pet_meta.feedback_details 
                WHERE message_id = ? AND feedback_type = ?
            """, [message_id, feedback_type]).fetchone()
            
            if result:
                return {
                    'remember_uprate': result[0],
                    'description_text': result[1],
                    'what_was_wrong': result[2],
                    'what_user_wanted': result[3],
                    'created_at': result[4],
                    'updated_at': result[5]
                }
            return None
        except Exception as e:
            print(f"ERROR - Failed to get feedback details: {e}")
            return None

    def delete_feedback_details(self, message_id: int, feedback_type: str = None) -> bool:
        """Delete feedback details for a message. If feedback_type is None, delete all."""
        try:
            if feedback_type:
                self.conn.execute("""
                    DELETE FROM pet_meta.feedback_details 
                    WHERE message_id = ? AND feedback_type = ?
                """, [message_id, feedback_type])
            else:
                self.conn.execute("""
                    DELETE FROM pet_meta.feedback_details 
                    WHERE message_id = ?
                """, [message_id])
            
            self.conn.commit()
            print(f"DEBUG - Deleted feedback details for message {message_id}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to delete feedback details: {e}")
            return False