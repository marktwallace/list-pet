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
            
            # Create data_artifacts table if it doesn't exist
            self.execute_query("""
                CREATE TABLE IF NOT EXISTS pet_meta.data_artifacts (
                    id INTEGER PRIMARY KEY,
                    message_id INTEGER,
                    artifact_type VARCHAR NOT NULL,
                    query_text TEXT,
                    metadata JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES pet_meta.message_log(id)
                )
            """)
            print("DEBUG - pet_meta.data_artifacts table created or already exists")
            
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
            
            # Create sequence for data_artifacts if it doesn't exist
            self.execute_query("""
                CREATE SEQUENCE IF NOT EXISTS pet_meta.data_artifacts_seq
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
            result = self.execute_query(f"""
                INSERT INTO pet_meta.message_log (id, role, message_text, has_dataframe, has_figure)
                VALUES (nextval('pet_meta.message_log_seq'), '{role}', $1, {has_dataframe}, {has_figure})
                RETURNING id
            """, params=[content])
            
            # Get the message ID for potential data artifact logging
            message_id = None
            if result is not None and isinstance(result, pd.DataFrame) and not result.empty:
                message_id = result.iloc[0]['id']
                
                # If this message has a dataframe or figure, log it as a data artifact
                if has_dataframe or has_figure:
                    self.log_data_artifact(message_id, message)
            
            print(f"DEBUG - Message logged to pet_meta.message_log: role={role}, has_dataframe={has_dataframe}, has_figure={has_figure}")
            return True
        except Exception as e:
            error_msg = f"Failed to log message: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Message logging traceback: {traceback.format_exc()}")
            return False
    
    def log_data_artifact(self, message_id, message):
        """Log a data artifact associated with a message"""
        try:
            # Determine artifact type
            artifact_type = None
            if "dataframe" in message and message["dataframe"] is not None:
                artifact_type = "dataframe"
            elif "figure" in message:
                artifact_type = "plot"
            elif "map_figure" in message:
                artifact_type = "map"
            else:
                print("WARNING - No recognizable data artifact in message")
                return False
                
            # Extract query text if available
            query_text = None
            if "query_text" in message:
                query_text = message["query_text"]
                
            # Build metadata JSON
            metadata = {}
            
            # For plots, include plot specifications
            if artifact_type == "plot" and "plot_spec" in message:
                metadata["plot_spec"] = message["plot_spec"]
            
            # For plots, also check for the older format
            elif artifact_type == "plot" and not "plot_spec" in message:
                # Try to extract plot spec from the figure data
                try:
                    if "figure" in message and message["figure"] is not None:
                        fig = message["figure"]
                        if hasattr(fig, "data") and len(fig.data) > 0:
                            # Extract basic plot info
                            plot_spec = {"type": fig.data[0].type}
                            metadata["plot_spec"] = plot_spec
                            print(f"DEBUG - Extracted plot type from figure: {plot_spec['type']}")
                except Exception as e:
                    print(f"WARNING - Failed to extract plot spec from figure: {str(e)}")
                
            # For maps, include map specifications
            if artifact_type == "map" and "map_spec" in message:
                metadata["map_spec"] = message["map_spec"]
                
            # Include dataframe info (column names, etc.)
            if "dataframe" in message and message["dataframe"] is not None:
                df = message["dataframe"]
                metadata["columns"] = df.columns.tolist()
                metadata["shape"] = list(df.shape)
                
                # Include a sample of the data for preview (first few rows)
                try:
                    sample_rows = min(5, len(df))
                    sample_data = df.head(sample_rows).to_dict(orient='records')
                    metadata["sample_data"] = sample_data
                    print(f"DEBUG - Included sample data ({sample_rows} rows) in metadata")
                except Exception as e:
                    print(f"WARNING - Failed to include sample data: {str(e)}")
                
            # Insert the data artifact
            self.execute_query(f"""
                INSERT INTO pet_meta.data_artifacts 
                (id, message_id, artifact_type, query_text, metadata)
                VALUES (
                    nextval('pet_meta.data_artifacts_seq'),
                    {message_id},
                    '{artifact_type}',
                    $1,
                    $2
                )
            """, params=[query_text, json.dumps(metadata)])
            
            print(f"DEBUG - Data artifact logged: type={artifact_type}, message_id={message_id}")
            return True
        except Exception as e:
            error_msg = f"Failed to log data artifact: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Data artifact logging traceback: {traceback.format_exc()}")
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
    
    def get_data_artifacts_for_message(self, message_id):
        """Get data artifacts associated with a message"""
        try:
            print(f"DEBUG - Getting data artifacts for message {message_id}")
            df, _ = self.execute_query(f"""
                SELECT id, artifact_type, query_text, metadata
                FROM pet_meta.data_artifacts
                WHERE message_id = {message_id}
            """)
            
            if df is None or df.empty:
                print(f"DEBUG - No data artifacts found for message {message_id}")
                return []
            
            print(f"DEBUG - Found {len(df)} data artifacts for message {message_id}")
            
            artifacts = []
            for _, row in df.iterrows():
                artifact = {
                    "id": row['id'],
                    "type": row['artifact_type'],
                    "query_text": row['query_text']
                }
                
                # Parse metadata JSON
                if row['metadata']:
                    try:
                        artifact["metadata"] = json.loads(row['metadata'])
                        print(f"DEBUG - Parsed metadata for artifact {row['id']}, type: {row['artifact_type']}")
                        
                        # Check for sample data
                        if "sample_data" in artifact["metadata"]:
                            print(f"DEBUG - Artifact {row['id']} has sample data with {len(artifact['metadata']['sample_data'])} rows")
                    except Exception as e:
                        print(f"ERROR - Failed to parse metadata JSON for artifact {row['id']}: {str(e)}")
                        artifact["metadata"] = {}
                        
                artifacts.append(artifact)
            
            return artifacts
        except Exception as e:
            error_msg = f"Failed to get data artifacts: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Get artifacts traceback: {traceback.format_exc()}")
            return []
    
    def repair_missing_data_artifacts(self):
        """Check for messages marked with data artifacts but missing entries in data_artifacts table"""
        try:
            print("DEBUG - Checking for messages with missing data artifacts")
            # Find messages marked as having dataframes or figures but no entries in data_artifacts
            df, _ = self.execute_query("""
                SELECT ml.id, ml.message_text, ml.has_dataframe, ml.has_figure
                FROM pet_meta.message_log ml
                LEFT JOIN pet_meta.data_artifacts da ON ml.id = da.message_id
                WHERE (ml.has_dataframe = TRUE OR ml.has_figure = TRUE)
                AND da.id IS NULL
            """)
            
            if df is None or df.empty:
                print("DEBUG - No inconsistencies found between message_log and data_artifacts")
                return 0
            
            print(f"DEBUG - Found {len(df)} messages with missing data artifacts")
            
            # For each message with missing artifacts, create a placeholder entry
            count = 0
            for _, row in df.iterrows():
                message_id = row['id']
                message_text = row['message_text']
                has_dataframe = row['has_dataframe']
                has_figure = row['has_figure']
                
                print(f"DEBUG - Repairing message {message_id}: has_dataframe={has_dataframe}, has_figure={has_figure}")
                
                # Try to extract SQL query from message text
                query_text = None
                sql_match = re.search(r"```(?:sql)?\s*\n?(.*?)\n?```", message_text, re.DOTALL)
                if sql_match:
                    query_text = sql_match.group(1).strip()
                    print(f"DEBUG - Extracted SQL query from message {message_id}")
                
                # Determine artifact type
                artifact_type = "dataframe" if has_dataframe else "plot" if has_figure else "unknown"
                
                # Create basic metadata
                metadata = {}
                
                # For dataframes, try to extract column info from message text
                if artifact_type == "dataframe":
                    # Look for column names in the message
                    cols_match = re.search(r"Columns:\s*(.*?)(?:\n|$)", message_text)
                    if cols_match:
                        cols_text = cols_match.group(1).strip()
                        columns = [col.strip() for col in cols_text.split(',')]
                        metadata["columns"] = columns
                        print(f"DEBUG - Extracted columns from message {message_id}: {columns}")
                    
                    # Look for shape info in the message
                    shape_match = re.search(r"(\d+)\s*rows\s*[×x]\s*(\d+)\s*columns", message_text)
                    if shape_match:
                        rows = int(shape_match.group(1))
                        cols = int(shape_match.group(2))
                        metadata["shape"] = [rows, cols]
                        print(f"DEBUG - Extracted shape from message {message_id}: {rows} rows × {cols} columns")
                
                # Insert the data artifact - removed artifact_id column
                self.execute_query(f"""
                    INSERT INTO pet_meta.data_artifacts 
                    (id, message_id, artifact_type, query_text, metadata)
                    VALUES (
                        nextval('pet_meta.data_artifacts_seq'),
                        {message_id},
                        '{artifact_type}',
                        $1,
                        $2
                    )
                """, params=[query_text, json.dumps(metadata)])
                
                count += 1
                print(f"DEBUG - Created placeholder data artifact for message {message_id}")
            
            print(f"DEBUG - Repaired {count} messages with missing data artifacts")
            return count
        except Exception as e:
            error_msg = f"Failed to repair missing data artifacts: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Repair traceback: {traceback.format_exc()}")
            return 0
    
    def load_messages(self):
        """Load messages from pet_meta.message_log"""
        try:
            # First, check and repair any inconsistencies
            self.repair_missing_data_artifacts()
            
            df, _ = self.execute_query("""
                SELECT id, role, message_text, has_dataframe, has_figure
                FROM pet_meta.message_log
                ORDER BY id ASC
            """)
            
            if df is None or df.empty:
                print("DEBUG - No messages found in pet_meta.message_log")
                return []
            
            print(f"DEBUG - Found {len(df)} messages in pet_meta.message_log")
            
            messages = []
            for _, row in df.iterrows():
                message = {
                    "role": row['role'],
                    "content": row['message_text']
                }
                
                # Add flags for data artifacts
                if row['has_dataframe'] or row['has_figure']:
                    message["had_data_artifact"] = True
                    message["message_id"] = row['id']
                    
                    print(f"DEBUG - Message {row['id']} had data artifact: has_dataframe={row['has_dataframe']}, has_figure={row['has_figure']}")
                    
                    # Get associated data artifacts
                    artifacts = self.get_data_artifacts_for_message(row['id'])
                    if artifacts:
                        print(f"DEBUG - Found {len(artifacts)} data artifacts for message {row['id']}")
                        message["data_artifacts"] = artifacts
                        
                        # For messages with dataframes, we'll add a placeholder dataframe
                        # This ensures the UI knows to render a dataframe component
                        for artifact in artifacts:
                            if artifact.get("type") == "dataframe":
                                # We don't have the actual dataframe data, but we can indicate
                                # that this message had a dataframe that can be regenerated
                                message["dataframe"] = None
                                print(f"DEBUG - Message {row['id']} had a dataframe artifact")
                                
                                # If we have sample data, create a preview dataframe
                                if "metadata" in artifact and "sample_data" in artifact["metadata"]:
                                    try:
                                        sample_data = artifact["metadata"]["sample_data"]
                                        if sample_data and len(sample_data) > 0:
                                            # Create a preview dataframe with "(preview)" suffix in the message
                                            message["content"] += "\n\n*(Preview data available)*"
                                            print(f"DEBUG - Added preview indicator to message {row['id']}")
                                    except Exception as e:
                                        print(f"WARNING - Failed to process sample data: {str(e)}")
                    else:
                        print(f"DEBUG - No data artifacts found for message {row['id']} despite has_dataframe={row['has_dataframe']}, has_figure={row['has_figure']}")
                
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

    def store_data_artifact(self, message_id, artifact_type, metadata, query_text=None):
        """Store a data artifact in the pet_meta.data_artifacts table"""
        try:
            print(f"DEBUG - Storing data artifact: type={artifact_type}, message_id={message_id}, has_query={query_text is not None}")
            
            # Convert metadata to JSON string
            metadata_json = json.dumps(metadata)
            
            # Check if metadata has sample data
            has_sample = "sample_data" in metadata and metadata["sample_data"] is not None
            print(f"DEBUG - Artifact metadata has sample data: {has_sample}")
            
            # Insert the data artifact
            result = self.execute_query(f"""
                INSERT INTO pet_meta.data_artifacts 
                (id, message_id, artifact_type, query_text, metadata)
                VALUES (
                    nextval('pet_meta.data_artifacts_seq'),
                    {message_id if message_id is not None else 'NULL'},
                    '{artifact_type}',
                    $1,
                    $2
                )
                RETURNING id
            """, params=[query_text, metadata_json])
            
            # Get the artifact ID
            artifact_db_id = None
            if result is not None and isinstance(result, pd.DataFrame) and not result.empty:
                artifact_db_id = result.iloc[0]['id']
                print(f"DEBUG - Data artifact stored with ID: {artifact_db_id}")
            
            return artifact_db_id
        except Exception as e:
            error_msg = f"Failed to store data artifact: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Store artifact traceback: {traceback.format_exc()}")
            return None

    def update_data_artifact_message_id(self, artifact_id, message_id):
        """Update the message_id for a data artifact"""
        try:
            print(f"DEBUG - Updating message_id for artifact {artifact_id} to {message_id}")
            self.execute_query(f"""
                UPDATE pet_meta.data_artifacts
                SET message_id = {message_id}
                WHERE id = {artifact_id}
            """)
            print(f"DEBUG - Updated message_id for artifact {artifact_id}")
            return True
        except Exception as e:
            error_msg = f"Failed to update data artifact message_id: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Update artifact traceback: {traceback.format_exc()}")
            return False

    def purge_database(self):
        """Completely reset the database by dropping and recreating all tables"""
        try:
            print("DEBUG - Purging database...")
            
            # Drop all tables and sequences
            self.execute_query("DROP TABLE IF EXISTS pet_meta.data_artifacts")
            self.execute_query("DROP TABLE IF EXISTS pet_meta.table_description")
            self.execute_query("DROP TABLE IF EXISTS pet_meta.message_log")
            self.execute_query("DROP SEQUENCE IF EXISTS pet_meta.data_artifacts_seq")
            self.execute_query("DROP SEQUENCE IF EXISTS pet_meta.table_description_seq")
            self.execute_query("DROP SEQUENCE IF EXISTS pet_meta.message_log_seq")
            
            # Recreate the schema
            self._initialize_pet_meta_schema()
            
            print("DEBUG - Database purged successfully")
            return True
        except Exception as e:
            error_msg = f"Failed to purge database: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Purge database traceback: {traceback.format_exc()}")
            return False 