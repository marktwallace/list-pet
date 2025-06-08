import duckdb
import streamlit as st
import traceback
from datetime import datetime

class MetadataDatabase:
    """Handles conversation and message persistence in DuckDB."""
    
    def __init__(self, db_path: str = None):
        """Initialize with a DuckDB connection.
        
        Args:
            db_path: Path to DuckDB file. If None, uses session state connection.
        """
        if db_path:
            self.conn = duckdb.connect(db_path)
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
                    FOREIGN KEY (conversation_id) REFERENCES pet_meta.conversations(id)
                )
            """)
            
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

    def log_message(self, message: dict, conversation_id: int) -> bool:
        """Store a message in the pet_meta.message_log table"""
        try:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            
            # Insert the message into the log
            self.conn.execute("""
                INSERT INTO pet_meta.message_log (id, conversation_id, role, content)
                VALUES (nextval('pet_meta.message_log_seq'), ?, ?, ?)
            """, [conversation_id, role, content])
            
            # Update conversation last_updated timestamp
            self.conn.execute("""
                UPDATE pet_meta.conversations
                SET last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, [conversation_id])
            
            print(f"DEBUG - Message logged to conversation {conversation_id}")
            return True
        except Exception as e:
            error_msg = f"Failed to log message: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message logging traceback: {traceback.format_exc()}")
            return False
    
    def load_messages(self, conversation_id: int) -> list[dict]:
        """Load messages for a specific conversation"""
        try:
            results = self.conn.execute("""
                SELECT role, content
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
                    "role": row[0],
                    "content": row[1]
                })
            
            print(f"DEBUG - Loaded {len(messages)} messages from conversation {conversation_id}")
            return messages
        except Exception as e:
            error_msg = f"Failed to load messages: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message loading traceback: {traceback.format_exc()}")
            return []

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
            
            print(f"DEBUG - Trimmed conversation {conversation_id} after message {message_id}")
            return True
        except Exception as e:
            error_msg = f"Failed to trim conversation: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Conversation trim traceback: {traceback.format_exc()}")
            return False 