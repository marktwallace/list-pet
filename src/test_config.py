import os
import shutil
import sys

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Test database path
TEST_DB_PATH = "test_data/test.duckdb"

# Ensure test data directory exists
os.makedirs(os.path.dirname(TEST_DB_PATH), exist_ok=True)

# Test database connection string
TEST_DB_CONNECTION = f"duckdb:{TEST_DB_PATH}"

# Test data setup SQL - to initialize the database with test data
TEST_INIT_SQL = [
    # Create pet_meta schema and tables
    """CREATE SCHEMA IF NOT EXISTS pet_meta""",
    
    """CREATE TABLE IF NOT EXISTS pet_meta.table_description (
        table_name TEXT PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        altered_at TIMESTAMP,
        request_text TEXT,
        row_count INTEGER DEFAULT 0
    )""",
    
    # Create test tables
    """CREATE TABLE IF NOT EXISTS test_table (
        id INTEGER, 
        name TEXT, 
        value FLOAT
    )""",
    
    """INSERT INTO test_table VALUES 
        (1, 'Test 1', 10.5), 
        (2, 'Test 2', 20.1), 
        (3, 'Test 3', 30.7)
    """
]

def reset_test_database():
    """Remove and recreate the test database file"""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

# Import Database class after setting up the path
from src.database import Database

class TestDatabase(Database):
    """Extended Database class for testing"""
    def __init__(self):
        """Initialize with test database connection"""
        # Skip the parent class __init__ to avoid connecting to the production database
        self.conn = None
        try:
            # Connect to the test database instead
            import duckdb
            self.conn = duckdb.connect(TEST_DB_PATH)
            print("DEBUG - Test database connection established successfully")
            # Initialize pet_meta schema and tables
            self._initialize_pet_meta_schema()
        except Exception as e:
            error_msg = f"Failed to connect to test database: {str(e)}"
            print(f"ERROR - {error_msg}")
            # Re-raise to prevent tests from running with a broken database connection
            raise RuntimeError(f"Test database connection failed: {str(e)}")
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None 