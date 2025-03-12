import unittest
import os
import sys
import pandas as pd

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.test_config import TEST_DB_PATH, TEST_INIT_SQL, reset_test_database, TestDatabase

class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        """Set up a fresh test database before each test"""
        # Reset the test database
        reset_test_database()
        
        # Create a fresh database instance
        self.db = TestDatabase()
        
        # Initialize with test data
        for sql in TEST_INIT_SQL:
            self.db.execute_query(sql)
    
    def tearDown(self):
        """Clean up after each test"""
        # Close database connection
        self.db.close()
    
    def test_execute_query(self):
        """Test basic query execution"""
        df, error = self.db.execute_query("SELECT * FROM test_table")
        self.assertIsNone(error)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3)
        self.assertEqual(df.columns.tolist(), ['id', 'name', 'value'])
    
    def test_execute_query_error(self):
        """Test handling of SQL errors"""
        df, error = self.db.execute_query("SELECT * FROM nonexistent_table")
        self.assertIsNotNone(error)
        self.assertIn("nonexistent_table", str(error))
    
    def test_table_creation_logging(self):
        """Test that table creation is properly logged"""
        # Log a table creation
        self.db.log_table_creation("new_test_table", "CREATE TABLE new_test_table (id INT)")
        
        # Verify the log entry
        df, error = self.db.execute_query(
            "SELECT * FROM pet_meta.table_description WHERE table_name = 'new_test_table'"
        )
        self.assertIsNone(error)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 1)
        self.assertEqual(df['table_name'].iloc[0], 'new_test_table')
        self.assertEqual(df['request_text'].iloc[0], 'CREATE TABLE new_test_table (id INT)')
    
    def test_get_table_row_count(self):
        """Test getting row count for a table"""
        # Create a new table with data
        self.db.execute_query("CREATE TABLE count_test (id INT)")
        self.db.execute_query("INSERT INTO count_test VALUES (1), (2), (3), (4), (5)")
        
        # Get the row count
        row_count = self.db.get_table_row_count("count_test")
        self.assertEqual(row_count, 5)

if __name__ == '__main__':
    unittest.main() 