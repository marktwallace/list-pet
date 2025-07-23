import duckdb
import os
import shutil
from datetime import datetime, timezone

class DuckDBAnalytic:
    def __init__(self, db_path: str, read_only: bool = False):
        """
        Initialize DuckDB connection.
        
        Args:
            db_path: Path to the DuckDB database file
            read_only: Whether to open in read-only mode
        """
        self.db_path = db_path
        self.read_only = read_only
        self.conn = None
        self.cached_timestamp = None
        
        # Connect initially
        self._connect()

    def _connect(self):
        """Establish database connection."""
        try:
            if self.read_only:
                self.conn = duckdb.connect(self.db_path, read_only=True)
                print(f"DEBUG - DuckDB analytic connection established in read-only mode: {self.db_path}")
            else:
                self.conn = duckdb.connect(self.db_path)
                print(f"DEBUG - DuckDB analytic connection established: {self.db_path}")
            
            # Cache the timestamp immediately after successful connection
            self.cached_timestamp = self._query_timestamp()
            
        except Exception as e:
            print(f"ERROR - Failed to connect to DuckDB: {e}")
            self.conn = None
            self.cached_timestamp = None
            raise

    def _ensure_connected(self):
        """Ensure we have an active connection."""
        if not self.conn:
            raise RuntimeError("Database connection not available")

    def check_and_swap(self):
        """Check for .new file and perform hot-swap if present."""
        new_file_path = f"{self.db_path}.new"
        
        if not os.path.exists(new_file_path):
            return False
            
        print(f"DEBUG - Hot-swap: .new file detected at {new_file_path}")
        
        try:
            # Close current connection to release file lock
            if self.conn:
                self.conn.close()
                print("DEBUG - Hot-swap: Closed current connection")
            
            # Create backup of current database
            backup_path = f"{self.db_path}.old"
            if os.path.exists(self.db_path):
                shutil.move(self.db_path, backup_path)
                print(f"DEBUG - Hot-swap: Moved {self.db_path} to {backup_path}")
            
            # Move new file to main location
            shutil.move(new_file_path, self.db_path)
            print(f"DEBUG - Hot-swap: Moved {new_file_path} to {self.db_path}")
            
            # Reconnect to new database (this will update cached_timestamp)
            self._connect()
            
            print(f"DEBUG - Hot-swap completed successfully. New timestamp: {self.cached_timestamp}")
            
            return True
            
        except Exception as e:
            print(f"ERROR - Hot-swap failed: {e}")
            # Try to restore from backup if swap failed
            backup_path = f"{self.db_path}.old"
            if os.path.exists(backup_path):
                try:
                    shutil.move(backup_path, self.db_path)
                    self._connect()
                    print("DEBUG - Restored from backup after failed hot-swap")
                except Exception as restore_error:
                    print(f"ERROR - Failed to restore from backup: {restore_error}")
            return False

    def execute_query(self, sql: str):
        """
        Execute a SQL query with hot-swap check.
        
        Returns:
            tuple: (DataFrame or None, error_message or None)
        """
        try:
            # Check for hot-swap opportunity before query
            self.check_and_swap()
            
            # Ensure we're connected
            self._ensure_connected()
            
            # Execute the query
            result = self.conn.execute(sql).fetchdf()
            
            return result, None
            
        except Exception as e:
            error_msg = f"SQL execution error: {str(e)}"
            print(f"ERROR - {error_msg}")
            return None, error_msg

    def _query_timestamp(self):
        """Query the database timestamp if configured. Only called when connection changes."""
        timestamp_query = os.environ.get("DB_TIMESTAMP_QUERY")
        if not timestamp_query:
            print("DEBUG - No DB_TIMESTAMP_QUERY configured, timestamp will be 'Unknown'")
            return "Unknown"
        
        try:
            print(f"DEBUG - Querying database timestamp with: {timestamp_query}")
            self._ensure_connected()
            result = self.conn.execute(timestamp_query).fetchone()
            if result and result[0]:
                # Convert to datetime if it's a string
                if isinstance(result[0], str):
                    try:
                        dt = datetime.fromisoformat(result[0].replace('Z', '+00:00'))
                        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        print(f"DEBUG - Database timestamp retrieved: {timestamp}")
                        return timestamp
                    except ValueError:
                        timestamp = str(result[0])
                        print(f"DEBUG - Database timestamp retrieved (raw): {timestamp}")
                        return timestamp
                # Handle datetime objects
                elif hasattr(result[0], 'strftime'):
                    if result[0].tzinfo is None:
                        # Assume UTC if no timezone
                        dt = result[0].replace(tzinfo=timezone.utc)
                    else:
                        dt = result[0]
                    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                    print(f"DEBUG - Database timestamp retrieved: {timestamp}")
                    return timestamp
                else:
                    timestamp = str(result[0])
                    print(f"DEBUG - Database timestamp retrieved (converted): {timestamp}")
                    return timestamp
            print("DEBUG - Database timestamp query returned no result")
            return "Unknown"
        except Exception as e:
            print(f"DEBUG - Error querying timestamp: {e}")
            return "Unknown"

    def get_timestamp(self):
        """Get the cached database timestamp."""
        return self.cached_timestamp or "Unknown"

    def get_connection_info(self) -> dict:
        """Get information about the DuckDB connection."""
        return {
            "type": "DuckDB",
            "path": self.db_path,
            "connected": self.conn is not None,
            "last_updated": self.get_timestamp()
        }

    def close(self):
        """Clean shutdown of the database connection."""
        if self.conn:
            try:
                self.conn.close()
                print("DEBUG - DuckDB connection closed")
            except Exception as e:
                print(f"DEBUG - Error during connection close: {e}")
            finally:
                self.conn = None
                self.cached_timestamp = None 