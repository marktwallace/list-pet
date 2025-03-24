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
            
            # Create message_log table if it doesn't exist
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS pet_meta.message_log (
                    id INTEGER PRIMARY KEY,
                    role VARCHAR,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create table_description table if it doesn't exist
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
            
            # Create sequence for message_log if it doesn't exist
            self.execute_query("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.message_log_seq
                START 1 INCREMENT 1
            """)
            
            # Create sequence for table_description if it doesn't exist
            self.execute_query("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.table_description_seq
                START 1 INCREMENT 1
            """)
            
        except Exception as e:
            error_msg = f"Failed to initialize pet_meta schema: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Schema initialization traceback: {traceback.format_exc()}")
            # Don't re-raise, as we want the app to continue even if metadata tables can't be created
    
    def log_message(self, message):
        """Store a message in the pet_meta.message_log table"""
        try:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            
            # Insert the message into the log
            self.execute_query("""
                INSERT INTO pet_meta.message_log (id, role, content)
                VALUES (nextval('pet_meta.message_log_seq'), ?, ?)
            """, params=[role, content])
            
            print(f"DEBUG - Message logged to pet_meta.message_log: role={role}")
            return True
        except Exception as e:
            error_msg = f"Failed to log message: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message logging traceback: {traceback.format_exc()}")
            return False
    
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
            
    def load_messages(self):
        """Load messages from pet_meta.message_log"""
        try:
            df, _ = self.execute_query("""
                SELECT role, content
                FROM pet_meta.message_log
                ORDER BY id ASC
            """)
            
            if df is None or df.empty:
                print("DEBUG - No messages found in pet_meta.message_log")
                return []
            
            messages = []
            for _, row in df.iterrows():
                message = {
                    "role": row['role'],
                    "content": row['content']
                }
                messages.append(message)
            
            print(f"DEBUG - Loaded {len(messages)} messages from pet_meta.message_log")
            return messages
        except Exception as e:
            error_msg = f"Failed to load messages: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message loading traceback: {traceback.format_exc()}")
            return []

    CREATE_TABLE_REGEX = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)"
    
    def execute_query(self, sql: str, params=None) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)"""
        try:
            # Check if this is a CREATE TABLE statement
            create_table_name = None
            match = re.search(self.CREATE_TABLE_REGEX, sql, re.IGNORECASE)
            if match:
                create_table_name = match.group(1)
                # print(f"DEBUG - Detected CREATE TABLE for {create_table_name}")
            
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
            
            # If it's a SELECT or SHOW statement and returns data, return the dataframe
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
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
                    #print("DEBUG - CREATE TABLE operation completed successfully")
                    # Get the most recent user message as the request_text
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