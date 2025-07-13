import duckdb
import os
import shutil
from datetime import datetime, timezone
import threading
import time

class DuckDBAnalytic:
    def __init__(self, db_path: str, read_only: bool = False, idle_timeout: int = 60):
        """
        Initialize DuckDB connection with idle management support.
        
        Args:
            db_path: Path to the DuckDB database file
            read_only: Whether to open in read-only mode
            idle_timeout: Seconds of inactivity before auto-closing connection (default 1 minute)
        """
        self.db_path = db_path
        self.read_only = read_only
        self.idle_timeout = idle_timeout
        self.conn = None
        self.last_activity = time.time()
        self.lock = threading.Lock()
        self.idle_timer = None
        
        print(f"DEBUG - DuckDB idle timeout: {idle_timeout}s")
        
        # Connect initially
        self._connect()
        
        # Start idle monitoring
        self._start_idle_monitor()

    def _connect(self):
        """Establish database connection."""
        try:
            if self.read_only:
                self.conn = duckdb.connect(self.db_path, read_only=True)
                print(f"DEBUG - DuckDB analytic connection established in read-only mode: {self.db_path}")
            else:
                self.conn = duckdb.connect(self.db_path)
                print(f"DEBUG - DuckDB analytic connection established: {self.db_path}")
                
            self.last_activity = time.time()
            
        except Exception as e:
            print(f"ERROR - Failed to connect to DuckDB: {e}")
            self.conn = None
            raise

    def _close_connection(self):
        """Close the database connection."""
        with self.lock:
            if self.conn:
                try:
                    self.conn.close()
                    print(f"DEBUG - DuckDB connection closed due to inactivity")
                except Exception as e:
                    print(f"DEBUG - Error closing DuckDB connection: {e}")
                finally:
                    self.conn = None

    def _start_idle_monitor(self):
        """Start the idle monitoring timer."""
        def check_idle():
            current_time = time.time()
            idle_duration = current_time - self.last_activity
            
            with self.lock:
                if self.conn and idle_duration > self.idle_timeout:
                    print(f"DEBUG - Closing connection after {idle_duration:.0f}s inactivity")
                    self._close_connection()
            
            # Schedule next check
            if hasattr(self, 'idle_timer'):  # Check if object still exists
                self.idle_timer = threading.Timer(30, check_idle)  # Check every 30 seconds 
                self.idle_timer.daemon = True
                self.idle_timer.start()
        
        # Start the first timer
        self.idle_timer = threading.Timer(30, check_idle)
        self.idle_timer.daemon = True
        self.idle_timer.start()
        print(f"DEBUG - Idle monitor started, connection will close after {self.idle_timeout}s of inactivity")

    def _ensure_connected(self):
        """Ensure we have an active connection, reconnecting if necessary."""
        with self.lock:
            if not self.conn:
                print("DEBUG - Reconnecting to database after idle closure")
                self._connect()
            self.last_activity = time.time()

    def check_and_swap(self):
        """Check for .new file and perform hot-swap if present."""
        new_file_path = f"{self.db_path}.new"
        
        if not os.path.exists(new_file_path):
            return False
            
        print(f"DEBUG - Hot-swap: .new file detected at {new_file_path}")
        
        with self.lock:
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
                
                # Reconnect to new database
                self._connect()
                
                # Get new timestamp
                new_timestamp = self.get_timestamp()
                print(f"DEBUG - Hot-swap completed successfully. New timestamp: {new_timestamp}")
                
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
        Execute a SQL query with hot-swap check and auto-reconnection.
        
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

    def get_timestamp(self):
        """Get the database timestamp if configured."""
        timestamp_query = os.environ.get("DB_TIMESTAMP_QUERY")
        if not timestamp_query:
            print("DEBUG - No DB_TIMESTAMP_QUERY configured")
            return "Unknown"
        
        try:
            self._ensure_connected()
            result = self.conn.execute(timestamp_query).fetchone()
            if result and result[0]:
                # Convert to datetime if it's a string
                if isinstance(result[0], str):
                    try:
                        dt = datetime.fromisoformat(result[0].replace('Z', '+00:00'))
                        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                    except ValueError:
                        return str(result[0])
                # Handle datetime objects
                elif hasattr(result[0], 'strftime'):
                    if result[0].tzinfo is None:
                        # Assume UTC if no timezone
                        dt = result[0].replace(tzinfo=timezone.utc)
                    else:
                        dt = result[0]
                    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    return str(result[0])
            return "Unknown"
        except Exception as e:
            print(f"DEBUG - Error getting timestamp: {e}")
            return "Unknown"

    def get_connection_info(self) -> dict:
        """Get information about the DuckDB connection."""
        return {
            "type": "DuckDB",
            "path": self.db_path,
            "connected": self.conn is not None,
            "last_updated": self.get_timestamp()
        }

    def close(self):
        """Clean shutdown of the database connection and idle monitor."""
        with self.lock:
            # Stop idle timer
            if self.idle_timer:
                self.idle_timer.cancel()
                print("DEBUG - Cancelled idle timer")
            
            # Close connection
            if self.conn:
                try:
                    self.conn.close()
                    print("DEBUG - DuckDB connection closed")
                except Exception as e:
                    print(f"DEBUG - Error during connection close: {e}")
                finally:
                    self.conn = None 