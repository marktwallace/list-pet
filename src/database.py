import duckdb
import streamlit as st
import pandas as pd
import traceback
from datetime import datetime
import re
import os
import psycopg2

class Database:
    def __init__(self):
        self.conn = st.session_state.get("conn")
        self.postgres_conn = None

        # Connect to PostgreSQL if POSTGRES_CONN_STR is set (after .env load)
        postgres_conn_str = os.environ.get("POSTGRES_CONN_STR")
        if postgres_conn_str:
            try:
                self.postgres_conn = psycopg2.connect(postgres_conn_str)
                print("DEBUG - Successfully connected to PostgreSQL.")
            except Exception as e:
                error_msg = f"Failed to connect to PostgreSQL: {str(e)}"
                print(f"ERROR - {error_msg}")
        else:
            print("DEBUG - POSTGRES_CONN_STR not set, PostgreSQL connection not attempted.")
    
    def initialize_pet_meta_schema(self):
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
            
            # Create table_description table
            self.conn.execute("""
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
            self.conn.execute("""
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

    def log_table_creation(self, table_name, request_text=None):
        """Log the creation of a new table in pet_meta.table_description"""
        try:
            # Check if the table already exists in our metadata
            df, _ = self.execute_query(f"""
                SELECT id FROM pet_meta.table_description 
                WHERE table_name = '{table_name}'
            """)
            
            safe_request_text = "" if request_text is None else request_text
            
            # Use direct connection execution to avoid recursion
            self.conn.execute("""
                INSERT INTO pet_meta.table_description 
                (id, table_name, description, request_text)
                VALUES (
                    nextval('pet_meta.table_description_seq'),
                    ?,
                    ?,
                    ?
                )
            """, [table_name, safe_request_text, safe_request_text])
            print(f"DEBUG - Inserted new table metadata for {table_name}")
            
            return True
        except Exception as e:
            error_msg = f"Failed to log table creation: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Table logging traceback: {traceback.format_exc()}")
            return False
            
    CREATE_TABLE_REGEX = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)"
    
    def execute_query(self, sql: str, params=None, description: str = None, target_db: str = "default") -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)
        Routes to DuckDB or PostgreSQL based on POSTGRES_CONN_STR or target_db.
        """
        actual_target_db = target_db
        if target_db == "default":
            if self.postgres_conn: # If PostgreSQL connection exists, default to it
                actual_target_db = "postgres"
            else:
                actual_target_db = "duckdb"
        
        print(f"DEBUG - Routing query to: {actual_target_db}. Original target: {target_db}, Postgres available: {bool(self.postgres_conn)}")

        if actual_target_db == "duckdb":
            return self._execute_duckdb_query(sql, params, description)
        elif actual_target_db == "postgres":
            if not self.postgres_conn:
                return None, "PostgreSQL connection not available."
            # The 'description' parameter is primarily for DuckDB table creation logging in pet_meta
            return self._execute_postgres_query(sql, params)
        else:
            return None, f"Unsupported target database: {actual_target_db}"

    def _execute_duckdb_query(self, sql: str, params=None, description: str = None) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL against DuckDB and return (dataframe, error_message)"""
        try:
            print(f"DEBUG - Database (DuckDB) executing SQL: {sql[:100]}...")
            create_table_name = None
            match = re.search(self.CREATE_TABLE_REGEX, sql, re.IGNORECASE)
            if match:
                create_table_name = match.group(1)
                print(f"DEBUG - Detected CREATE TABLE for: {create_table_name} (DuckDB)")
            
            try:
                if params is not None:
                    print(f"DEBUG - Executing with params: {params} (DuckDB)")
                    result = self.conn.execute(sql, params)
                else:
                    result = self.conn.execute(sql)
                print("DEBUG - SQL execution successful (DuckDB)")
            except Exception as e:
                error_msg = f"SQL Error (DuckDB): {str(e)}"
                print(f"ERROR - {error_msg}")
                print(f"ERROR - SQL execution traceback (DuckDB): {traceback.format_exc()}")
                return None, error_msg
            
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")) or "RETURNING" in sql.upper():
                try:
                    df = result.df()
                    print(f"DEBUG - Query returned dataframe with {len(df)} rows and {len(df.columns)} columns (DuckDB)")
                    return df, None
                except Exception as e:
                    error_msg = f"Error displaying results (DuckDB): {str(e)}"
                    print(f"ERROR - {error_msg}")
                    print(f"ERROR - Result display traceback (DuckDB): {traceback.format_exc()}")
                    return None, error_msg
            else:
                if create_table_name and not create_table_name.startswith("pet_meta."):
                    print(f"DEBUG - Logging creation of table: {create_table_name} (DuckDB)")
                    self.log_table_creation(create_table_name, description or "")
                return None, None
                
        except Exception as e:
            error_msg = f"SQL Error (DuckDB): {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback (DuckDB): {traceback.format_exc()}")
            if "no such table" in str(e).lower():
                error_msg += "\n The table you\'re trying to query doesn\'t exist in DuckDB. Use SHOW TABLES to see available tables or CREATE TABLE to create a new one."
            elif "not found" in str(e).lower() and "column" in str(e).lower():
                error_msg += "\n One or more columns in your query don\'t exist in the DuckDB table. Use DESCRIBE [table_name] to see available columns."
            return None, error_msg

    def _execute_postgres_query(self, sql: str, params=None) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL against PostgreSQL and return (dataframe, error_message)"""
        try:
            print(f"DEBUG - Database (PostgreSQL) executing SQL: {sql[:100]}...")
            with self.postgres_conn.cursor() as cur:
                if params is not None:
                    print(f"DEBUG - Executing with params: {params} (PostgreSQL)")
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                
                # Commit DML/DDL statements if not a SELECT
                if not sql.strip().upper().startswith("SELECT") and not "RETURNING" in sql.upper():
                    self.postgres_conn.commit()
                    print("DEBUG - SQL execution successful, changes committed (PostgreSQL)")
                    return None, None

                # For SELECT or RETURNING statements
                if cur.description: # Check if there are columns to fetch
                    colnames = [desc[0] for desc in cur.description]
                    df = pd.DataFrame(cur.fetchall(), columns=colnames)
                    print(f"DEBUG - Query returned dataframe with {len(df)} rows and {len(df.columns)} columns (PostgreSQL)")
                    return df, None
                else: # For statements like INSERT without RETURNING, or other commands that don't return rows
                    print("DEBUG - SQL execution successful, no rows returned (PostgreSQL)")
                    # self.postgres_conn.commit() # Ensure commit for DDL/DML that might not have RETURNING
                    return None, None

        except psycopg2.Error as e:
            self.postgres_conn.rollback() # Rollback on error
            error_msg = f"SQL Error (PostgreSQL): {e.pgcode} - {e.pgerror}"
            if e.diag and e.diag.message_detail:
                error_msg += f" Detail: {e.diag.message_detail}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback (PostgreSQL): {traceback.format_exc()}")
            return None, error_msg
        except Exception as e:
            if self.postgres_conn and not self.postgres_conn.closed:
                 self.postgres_conn.rollback() # Rollback on generic error if connection is still open
            error_msg = f"Generic Error during PostgreSQL query: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback (PostgreSQL): {traceback.format_exc()}")
            return None, error_msg

    def get_table_metadata(self) -> pd.DataFrame:
        """Get metadata for all user tables, combining system catalog with our descriptions"""
        try:
            print("DEBUG - Starting table metadata query")
            query = """
                WITH user_tables AS (
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'main'
                        AND table_name NOT LIKE 'pet_meta%'
                )
                SELECT 
                    t.table_name,
                    COALESCE(d.description, 'No description available. Use DESCRIBE ' || t.table_name || ' to see columns.') as description
                FROM user_tables t
                LEFT JOIN pet_meta.table_description d ON t.table_name = d.table_name
                ORDER BY t.table_name;
            """
            print("DEBUG - Executing metadata query with description join")
            df, err = self.execute_query(query)
            
            if err:
                print(f"ERROR - Failed to get table metadata: {err}")
                return pd.DataFrame(columns=['table_name', 'description'])
                
            print(f"DEBUG - Query successful, got DataFrame: {df.shape if df is not None else 'None'}")
            if df is not None:
                table_descriptions = ['no tables'] if df.empty else [f"{row['table_name']}: {row['description']}" for _, row in df.iterrows()]
                print("DEBUG - Tables with descriptions:", table_descriptions)
                
            return df if df is not None else pd.DataFrame(columns=['table_name', 'description'])
            
        except Exception as e:
            print(f"ERROR - Exception getting table metadata: {str(e)}")
            print(f"ERROR - Table metadata traceback: {traceback.format_exc()}")
            return pd.DataFrame(columns=['table_name', 'description'])

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