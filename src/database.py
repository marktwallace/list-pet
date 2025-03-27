import duckdb
import streamlit as st
import pandas as pd
import traceback
from datetime import datetime
import re

class Database:
    def __init__(self):
        self.conn = st.session_state.get("conn")
    
    def initialize_pet_meta_schema(self):
        """Initialize pet_meta schema and tables if they don't exist"""
        print("DEBUG - Initializing pet_meta schema")
        try:
            # Create schema if it doesn't exist
            self.execute_query("CREATE SCHEMA IF NOT EXISTS pet_meta")
            
            # Create sequences
            self.execute_query("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.conversation_seq
                START 1 INCREMENT 1
            """)
            
            self.execute_query("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.message_log_seq
                START 1 INCREMENT 1
            """)
            
            # Create conversations table
            self.execute_query("""
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
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS pet_meta.message_log (
                    id INTEGER PRIMARY KEY,
                    conversation_id INTEGER NOT NULL,
                    role VARCHAR,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES pet_meta.conversations(id)
                )
            """)
            
            # Create table_description table
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS pet_meta.table_description (
                    id INTEGER PRIMARY KEY,
                    table_name VARCHAR NOT NULL,
                    description TEXT,
                    request_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    altered_at TIMESTAMP
                )
            """)
            
            # Create sequence for table_description
            self.execute_query("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.table_description_seq
                START 1 INCREMENT 1
            """)
            
        except Exception as e:
            error_msg = f"Failed to initialize pet_meta schema: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Schema initialization traceback: {traceback.format_exc()}")
            # Don't re-raise, as we want the app to continue even if metadata tables can't be created
    
    def create_conversation(self, title: str) -> int:
        """Create a new conversation and return its ID"""
        try:
            result, err = self.execute_query("""
                INSERT INTO pet_meta.conversations (id, title)
                VALUES (nextval('pet_meta.conversation_seq'), ?)
                RETURNING id
            """, params=[title])
            
            if err:
                print(f"ERROR - Failed to create conversation: {err}")
                return None
                
            if result is not None and not result.empty:
                # Convert numpy.int32 to Python int
                conversation_id = int(result.iloc[0]['id'])
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
            # Ensure conversation_id is a Python int
            params.append(int(conversation_id))
            
            query = f"""
                UPDATE pet_meta.conversations 
                SET {', '.join(updates)}
                WHERE id = ?
            """
            
            self.execute_query(query, params=params)
            print(f"DEBUG - Updated conversation {conversation_id}")
            return True
        except Exception as e:
            print(f"ERROR - Failed to update conversation: {str(e)}")
            print(f"ERROR - Conversation update traceback: {traceback.format_exc()}")
            return False

    def get_conversations(self, include_archived: bool = False) -> pd.DataFrame:
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
            
            df, err = self.execute_query(query)
            if err:
                print(f"ERROR - Failed to get conversations: {err}")
                return pd.DataFrame()
            return df
        except Exception as e:
            print(f"ERROR - Failed to get conversations: {str(e)}")
            print(f"ERROR - Get conversations traceback: {traceback.format_exc()}")
            return pd.DataFrame()

    def log_message(self, message: dict, conversation_id: int) -> bool:
        """Store a message in the pet_meta.message_log table"""
        try:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            
            # Ensure conversation_id is a Python int
            conversation_id = int(conversation_id)
            
            # Insert the message into the log
            self.execute_query("""
                INSERT INTO pet_meta.message_log (id, conversation_id, role, content)
                VALUES (nextval('pet_meta.message_log_seq'), ?, ?, ?)
            """, params=[conversation_id, role, content])
            
            # Update conversation last_updated timestamp
            self.execute_query("""
                UPDATE pet_meta.conversations
                SET last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, params=[conversation_id])
            
            print(f"DEBUG - Message logged to conversation {conversation_id}")
            return True
        except Exception as e:
            error_msg = f"Failed to log message: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message logging traceback: {traceback.format_exc()}")
            return False
    
    def load_messages(self, conversation_id: int) -> list:
        """Load messages for a specific conversation"""
        try:
            # Ensure conversation_id is a Python int
            conversation_id = int(conversation_id)
            
            df, err = self.execute_query("""
                SELECT role, content
                FROM pet_meta.message_log
                WHERE conversation_id = ?
                ORDER BY id ASC
            """, params=[conversation_id])
            
            if df is None or df.empty:
                print(f"DEBUG - No messages found for conversation {conversation_id}")
                return []
            
            messages = []
            for _, row in df.iterrows():
                message = {
                    "role": row['role'],
                    "content": row['content']
                }
                messages.append(message)
            
            print(f"DEBUG - Loaded {len(messages)} messages from conversation {conversation_id}")
            return messages
        except Exception as e:
            error_msg = f"Failed to load messages: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message loading traceback: {traceback.format_exc()}")
            return []

    def log_table_creation(self, table_name, request_text=None):
        """Log the creation of a new table in pet_meta.table_description"""
        try:
            # Check if the table already exists in our metadata
            df, _ = self.execute_query(f"""
                SELECT id FROM pet_meta.table_description 
                WHERE table_name = '{table_name}'
            """)
            
            safe_request_text = "" if request_text is None else request_text
            self.execute_query(f"""
                INSERT INTO pet_meta.table_description 
                (id, table_name, request_text)
                VALUES (
                    nextval('pet_meta.table_description_seq'),
                    '{table_name}',
                    $1
                )
            """, params=[safe_request_text])
            print(f"DEBUG - Inserted new table metadata for {table_name}")
            
            return True
        except Exception as e:
            error_msg = f"Failed to log table creation: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Table logging traceback: {traceback.format_exc()}")
            return False
            
    CREATE_TABLE_REGEX = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)"
    
    def execute_query(self, sql: str, params=None) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)"""
        try:
            # Check if this is a CREATE TABLE statement
            create_table_name = None
            match = re.search(self.CREATE_TABLE_REGEX, sql, re.IGNORECASE)
            if match:
                create_table_name = match.group(1)
            
            # Execute the query
            try:
                if params is not None:
                    result = self.conn.execute(sql, params)
                else:
                    result = self.conn.execute(sql)
            except Exception as e:
                error_msg = f"SQL Error: {str(e)}"
                print(f"ERROR - {error_msg}")
                print(f"ERROR - SQL execution traceback: {traceback.format_exc()}")
                return None, error_msg
            
            # If it's a SELECT, SHOW, DESCRIBE or RETURNING statement, return the dataframe
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")) or "RETURNING" in sql.upper():
                try:
                    df = result.df()
                    print(f"DEBUG - Query returned dataframe with {len(df)} rows and {len(df.columns)} columns")
                    return df, None
                except Exception as e:
                    error_msg = f"Error displaying results: {str(e)}"
                    print(f"ERROR - {error_msg}")
                    print(f"ERROR - Result display traceback: {traceback.format_exc()}")
                    return None, error_msg
            else:
                # For non-SELECT statements
                # Special case for CREATE TABLE to log metadata
                if create_table_name and not create_table_name.startswith("pet_meta."):
                    request_text = None
                    self.log_table_creation(create_table_name, request_text)
                
                # For all successful non-SELECT operations, return None for the error message
                return None, None
                    
        except Exception as e:
            error_msg = f"SQL Error: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback: {traceback.format_exc()}")
            
            # Provide more specific guidance based on the error type
            if "no such table" in str(e).lower():
                error_msg += """               
                    The table you're trying to query doesn't exist. 
                    Use SHOW TABLES to see available tables or 
                    CREATE TABLE to create a new one.
                """
            elif "not found" in str(e).lower() and "column" in str(e).lower():
                error_msg += """
                    One or more columns in your query don't exist in the table. 
                    Use DESCRIBE [table_name] to see available columns.
                """
            
            return None, error_msg 