import psycopg2
import pandas as pd
import traceback
from typing import Optional, Tuple

from .analytic_database import AnalyticDatabase

class PostgreSQLAnalytic(AnalyticDatabase):
    """PostgreSQL implementation of analytic database operations."""
    
    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL connection.
        
        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string
        self.conn = None
        self._connect()
    
    def _connect(self):
        """Establish connection to PostgreSQL."""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            print(f"DEBUG - PostgreSQL analytic connection established")
        except Exception as e:
            print(f"ERROR - Failed to connect to PostgreSQL: {str(e)}")
            raise
    
    def execute_query(self, sql: str, params: Optional[list] = None) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Execute SQL against PostgreSQL and return (dataframe, error_message)"""
        try:
            print(f"DEBUG - PostgreSQL Analytic executing SQL: {sql[:100]}...")
            
            with self.conn.cursor() as cur:
                if params is not None:
                    print(f"DEBUG - Executing with params: {params} (PostgreSQL Analytic)")
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                
                # Commit DML/DDL statements if not a SELECT
                if not sql.strip().upper().startswith("SELECT") and not "RETURNING" in sql.upper():
                    self.conn.commit()
                    print("DEBUG - SQL execution successful, changes committed (PostgreSQL Analytic)")
                    return None, None

                # For SELECT or RETURNING statements
                if cur.description:  # Check if there are columns to fetch
                    colnames = [desc[0] for desc in cur.description]
                    df = pd.DataFrame(cur.fetchall(), columns=colnames)
                    print(f"DEBUG - Query returned dataframe with {len(df)} rows and {len(df.columns)} columns (PostgreSQL Analytic)")
                    return df, None
                else:  # For statements like INSERT without RETURNING, or other commands that don't return rows
                    print("DEBUG - SQL execution successful, no rows returned (PostgreSQL Analytic)")
                    return None, None

        except psycopg2.Error as e:
            if self.conn and not self.conn.closed:
                self.conn.rollback()  # Rollback on error
            
            error_msg = f"SQL Error (PostgreSQL Analytic): {e.pgcode} - {e.pgerror}"
            if e.diag and e.diag.message_detail:
                error_msg += f" Detail: {e.diag.message_detail}"
            
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback (PostgreSQL Analytic): {traceback.format_exc()}")
            return None, error_msg
            
        except Exception as e:
            if self.conn and not self.conn.closed:
                self.conn.rollback()  # Rollback on generic error if connection is still open
            
            error_msg = f"Generic Error during PostgreSQL query: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback (PostgreSQL Analytic): {traceback.format_exc()}")
            return None, error_msg
    
    def get_connection_info(self) -> dict:
        """Get information about the PostgreSQL connection."""
        try:
            # Parse connection string to get basic info (safely)
            info = {"type": "PostgreSQL", "connected": self.conn is not None and not self.conn.closed}
            
            if self.conn and not self.conn.closed:
                # Get database name and host if available
                with self.conn.cursor() as cur:
                    cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port()")
                    result = cur.fetchone()
                    if result:
                        info["database"] = result[0]
                        info["host"] = result[1] or "localhost"
                        info["port"] = result[2] or 5432
            
            return info
        except Exception as e:
            return {
                "type": "PostgreSQL", 
                "connected": False,
                "error": f"Failed to get connection info: {str(e)}"
            }
    
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """Test if the PostgreSQL connection is working."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("SELECT 1 as test")
                result = cur.fetchone()
                if result and result[0] == 1:
                    return True, None
                else:
                    return False, "Connection test returned unexpected result"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"
    
    def close(self):
        """Close the PostgreSQL connection."""
        if self.conn and not self.conn.closed:
            self.conn.close()
            print(f"DEBUG - PostgreSQL analytic connection closed") 