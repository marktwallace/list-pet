#!/usr/bin/env python3
"""
Standalone script to checkpoint a DuckDB database and merge WAL file.
Usage: python checkpoint_db.py <path_to_database>
"""

import sys
import os
import duckdb

def checkpoint_database(db_path):
    """Checkpoint a DuckDB database to merge WAL file."""
    if not os.path.exists(db_path):
        print(f"ERROR: Database file not found: {db_path}")
        return False
    
    try:
        print(f"Connecting to database: {db_path}")
        conn = duckdb.connect(db_path)
        
        print("Performing WAL checkpoint...")
        conn.execute("PRAGMA force_checkpoint")
        
        print("Checkpoint completed successfully!")
        conn.close()
        return True
    except Exception as e:
        print(f"ERROR: Failed to checkpoint database: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python checkpoint_db.py <path_to_database>")
        print("Example: python checkpoint_db.py db/conversations.duckdb")
        sys.exit(1)
    
    db_path = sys.argv[1]
    success = checkpoint_database(db_path)
    sys.exit(0 if success else 1) 