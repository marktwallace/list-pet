import duckdb
import streamlit as st
import pandas as pd
import os
import traceback
import json
from datetime import datetime
import re

@st.cache_resource
def get_database():
    """Get or create database connection"""
    os.makedirs("db", exist_ok=True)
    return Database()

class Database:
    def __init__(self):
        try:
            self.conn = duckdb.connect('db/list_pet.db')
            print("DEBUG - Database connection established successfully")
            # Initialize pet_meta schema and tables
            self._initialize_pet_meta_schema()
        except Exception as e:
            error_msg = f"Failed to connect to database: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Database connection traceback: {traceback.format_exc()}")
            # Re-raise to prevent app from starting with a broken database connection
            raise RuntimeError(f"Database connection failed: {str(e)}. Please check if the database file is accessible.")
    
    def _initialize_pet_meta_schema(self):
        """Initialize pet_meta schema and tables if they don't exist"""
        try:
            # Create schema if it doesn't exist
            self.execute_query("CREATE SCHEMA IF NOT EXISTS pet_meta")
            print("DEBUG - pet_meta schema created or already exists")
            
            # Create message_log table if it doesn't exist
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS pet_meta.message_log (
                    id INTEGER PRIMARY KEY,
                    role VARCHAR,
                    message_text TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    has_dataframe BOOLEAN DEFAULT FALSE,
                    has_figure BOOLEAN DEFAULT FALSE
                )
            """)
            print("DEBUG - pet_meta.message_log table created or already exists")
            
            # Create table_description table if it doesn't exist
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS pet_meta.table_description (
                    id INTEGER PRIMARY KEY,
                    table_name VARCHAR NOT NULL,
                    description TEXT,
                    request_text TEXT,
                    row_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    altered_at TIMESTAMP
                )
            """)
            print("DEBUG - pet_meta.table_description table created or already exists")
            
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
            has_dataframe = "dataframe" in message and message["dataframe"] is not None
            has_figure = "figure" in message or "map_figure" in message
            
            # Insert the message into the log
            self.execute_query(f"""
                INSERT INTO pet_meta.message_log (id, role, message_text, has_dataframe, has_figure)
                VALUES (nextval('pet_meta.message_log_seq'), '{role}', $1, {has_dataframe}, {has_figure})
            """, params=[content])
            
            print(f"DEBUG - Message logged to pet_meta.message_log: role={role}, has_dataframe={has_dataframe}, has_figure={has_figure}")
            return True
        except Exception as e:
            error_msg = f"Failed to log message: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message logging traceback: {traceback.format_exc()}")
            return False
    
    def log_table_creation(self, table_name, request_text=None, row_count=None):
        """Log the creation of a new table in pet_meta.table_description"""
        try:
            # Check if the table already exists in our metadata
            df, _ = self.execute_query(f"""
                SELECT id FROM pet_meta.table_description 
                WHERE table_name = '{table_name}'
            """)
            
            if df is not None and not df.empty:
                # Table already exists in metadata, update it
                self.execute_query(f"""
                    UPDATE pet_meta.table_description
                    SET altered_at = CURRENT_TIMESTAMP, 
                        row_count = {row_count if row_count is not None else 'NULL'}
                    WHERE table_name = '{table_name}'
                """)
                print(f"DEBUG - Updated table metadata for {table_name}")
            else:
                # New table, insert metadata
                self.execute_query(f"""
                    INSERT INTO pet_meta.table_description 
                    (id, table_name, request_text, row_count)
                    VALUES (
                        nextval('pet_meta.table_description_seq'),
                        '{table_name}',
                        $1,
                        {row_count if row_count is not None else 'NULL'}
                    )
                """, params=[request_text])
                print(f"DEBUG - Inserted new table metadata for {table_name}")
            
            return True
        except Exception as e:
            error_msg = f"Failed to log table creation: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Table logging traceback: {traceback.format_exc()}")
            return False
    
    def update_table_description(self, table_name, description):
        """Update the description for a table in pet_meta.table_description"""
        try:
            self.execute_query(f"""
                UPDATE pet_meta.table_description
                SET description = $1,
                    altered_at = CURRENT_TIMESTAMP
                WHERE table_name = '{table_name}'
            """, params=[description])
            print(f"DEBUG - Updated description for table {table_name}")
            return True
        except Exception as e:
            error_msg = f"Failed to update table description: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Description update traceback: {traceback.format_exc()}")
            return False
    
    def get_table_row_count(self, table_name):
        """Get the row count for a table"""
        try:
            # Extract schema and table name
            parts = table_name.split('.')
            if len(parts) == 2:
                schema, table = parts
                query = f"SELECT COUNT(*) as count FROM {schema}.{table}"
            else:
                query = f"SELECT COUNT(*) as count FROM {table_name}"
            
            df, _ = self.execute_query(query)
            if df is not None and not df.empty:
                return df.iloc[0]['count']
            return 0
        except Exception as e:
            print(f"ERROR - Failed to get row count for {table_name}: {str(e)}")
            return 0
    
    def load_messages(self):
        """Load messages from pet_meta.message_log"""
        try:
            df, _ = self.execute_query("""
                SELECT role, message_text, has_dataframe, has_figure
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
                    "content": row['message_text']
                }
                # Note: We can't restore actual dataframes or figures,
                # but we can flag that they existed
                messages.append(message)
            
            print(f"DEBUG - Loaded {len(messages)} messages from pet_meta.message_log")
            return messages
        except Exception as e:
            error_msg = f"Failed to load messages: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message loading traceback: {traceback.format_exc()}")
            return []
    
    def execute_query(self, sql: str, params=None) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)"""
        try:
            # Check if this is a CREATE TABLE statement
            is_create_table = bool(re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)", sql, re.IGNORECASE))
            table_name = None
            
            if is_create_table:
                # Extract the table name
                match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
                if match:
                    table_name = match.group(1)
                    print(f"DEBUG - Detected CREATE TABLE for {table_name}")
            
            # Execute the query
            if params:
                result = self.conn.execute(sql, params)
            else:
                result = self.conn.execute(sql)
            
            # If it's a SELECT or SHOW statement and returns data, return the dataframe
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
                try:
                    df = result.df()
                    if not df.empty:
                        print(f"DEBUG - Query returned {len(df)} rows with columns: {df.columns.tolist()}")
                        return df, None
                    else:
                        message = "Query returned no rows."
                        print(f"DEBUG - {message}")
                        return None, message
                except Exception as e:
                    error_msg = f"Error displaying results: {str(e)}"
                    print(f"ERROR - {error_msg}")
                    print(f"ERROR - Result display traceback: {traceback.format_exc()}")
                    return None, error_msg
            else:
                # For non-SELECT statements, provide information about the operation
                # But don't treat these as errors for internal processing
                if sql.strip().upper().startswith("INSERT"):
                    return None, "INSERT operation completed."
                elif sql.strip().upper().startswith("UPDATE"):
                    message = "UPDATE operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                elif sql.strip().upper().startswith("DELETE"):
                    message = "DELETE operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                elif sql.strip().upper().startswith("CREATE"):
                    # For CREATE statements, return None for the error message
                    # This allows metadata initialization to work correctly
                    print("DEBUG - CREATE operation completed successfully")
                    
                    # If this was a CREATE TABLE, log it in our metadata
                    if table_name and not table_name.startswith("pet_meta."):
                        # Get the most recent user message as the request_text
                        request_text = None
                        # We'll update the row count later when data is inserted
                        self.log_table_creation(table_name, request_text)
                    
                    return None, None
                elif sql.strip().upper().startswith("DROP"):
                    message = "DROP operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                elif sql.strip().upper().startswith("ALTER"):
                    message = "ALTER operation completed."
                    print(f"DEBUG - {message}")
                    
                    # Check if this is altering a table
                    match = re.search(r"ALTER\s+TABLE\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
                    if match:
                        table_name = match.group(1)
                        if not table_name.startswith("pet_meta."):
                            # Update the altered_at timestamp
                            self.execute_query(f"""
                                UPDATE pet_meta.table_description
                                SET altered_at = CURRENT_TIMESTAMP
                                WHERE table_name = '{table_name}'
                            """)
                    
                    return None, message
                else:
                    message = "Operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                    
        except Exception as e:
            error_msg = f"SQL Error: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback: {traceback.format_exc()}")
            
            # Provide more specific guidance based on the error type
            if "no such table" in str(e).lower():
                error_msg += "\n\nThe table you're trying to query doesn't exist. Use SHOW TABLES to see available tables or CREATE TABLE to create a new one."
            elif "syntax error" in str(e).lower():
                error_msg += "\n\nThere's a syntax error in your SQL query. Please check your query syntax and try again."
            elif "not found" in str(e).lower() and "column" in str(e).lower():
                error_msg += "\n\nOne or more columns in your query don't exist in the table. Use DESCRIBE [table_name] to see available columns."
            elif "constraint" in str(e).lower() and "violation" in str(e).lower():
                error_msg += "\n\nYour query violates a constraint (like a unique key or foreign key). Please check your data and try again."
            
            return None, error_msg 