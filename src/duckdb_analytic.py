import duckdb
import pandas as pd
import traceback
import re
from typing import Optional, Tuple

class DuckDBAnalytic:
    """DuckDB implementation of analytic database operations."""
    
    CREATE_TABLE_REGEX = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)"
    
    def __init__(self, db_path: str, read_only: bool = False):
        """
        Initialize DuckDB connection.
        
        Args:
            db_path: Path to DuckDB file
            read_only: Connect in read-only mode
        """
        self.db_path = db_path
        self.read_only = read_only
        self.conn = None
        self._connect()
    
    def _connect(self):
        """Establish connection to DuckDB."""
        try:
            self.conn = duckdb.connect(self.db_path, read_only=self.read_only)
            mode = "read-only" if self.read_only else "read-write"
            print(f"DEBUG - DuckDB analytic connection established in {mode} mode: {self.db_path}")
        except Exception as e:
            print(f"ERROR - Failed to connect to DuckDB: {str(e)}")
            raise
    
    def execute_query(self, sql: str, params: Optional[list] = None) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Execute SQL against DuckDB and return (dataframe, error_message)"""
        try:
            print(f"DEBUG - DuckDB Analytic executing SQL: {sql[:100]}...")
            
            # Check for CREATE TABLE statements
            create_table_name = None
            match = re.search(self.CREATE_TABLE_REGEX, sql, re.IGNORECASE)
            if match:
                create_table_name = match.group(1)
                print(f"DEBUG - Detected CREATE TABLE for: {create_table_name} (DuckDB Analytic)")
            
            # Execute the query
            try:
                if params is not None:
                    print(f"DEBUG - Executing with params: {params} (DuckDB Analytic)")
                    result = self.conn.execute(sql, params)
                else:
                    result = self.conn.execute(sql)
                print("DEBUG - SQL execution successful (DuckDB Analytic)")
            except Exception as e:
                error_msg = f"SQL Error (DuckDB Analytic): {str(e)}"
                print(f"ERROR - {error_msg}")
                print(f"ERROR - SQL execution traceback (DuckDB Analytic): {traceback.format_exc()}")
                return None, error_msg
            
            # Handle different query types
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")) or "RETURNING" in sql.upper():
                try:
                    df = result.df()
                    print(f"DEBUG - Query returned dataframe with {len(df)} rows and {len(df.columns)} columns (DuckDB Analytic)")
                    return df, None
                except Exception as e:
                    error_msg = f"Error displaying results (DuckDB Analytic): {str(e)}"
                    print(f"ERROR - {error_msg}")
                    print(f"ERROR - Result display traceback (DuckDB Analytic): {traceback.format_exc()}")
                    return None, error_msg
            else:
                if create_table_name:
                    print(f"DEBUG - Created table: {create_table_name} (DuckDB Analytic)")
                return None, None
                
        except Exception as e:
            error_msg = f"SQL Error (DuckDB Analytic): {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback (DuckDB Analytic): {traceback.format_exc()}")
            
            # Add helpful error messages
            if "no such table" in str(e).lower():
                error_msg += "\nThe table you're trying to query doesn't exist in DuckDB. Use SHOW TABLES to see available tables or CREATE TABLE to create a new one."
            elif "not found" in str(e).lower() and "column" in str(e).lower():
                error_msg += "\nOne or more columns in your query don't exist in the DuckDB table. Use DESCRIBE [table_name] to see available columns."
            
            return None, error_msg
    
    def get_connection_info(self) -> dict:
        """Get information about the DuckDB connection."""
        return {
            "type": "DuckDB",
            "path": self.db_path,
            "connected": self.conn is not None
        }
    
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """Test if the DuckDB connection is working."""
        try:
            # Simple test query
            result = self.conn.execute("SELECT 1 as test").fetchone()
            if result and result[0] == 1:
                return True, None
            else:
                return False, "Connection test returned unexpected result"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    def close(self):
        """Close the DuckDB connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            print(f"DEBUG - DuckDB analytic connection closed: {self.db_path}") 