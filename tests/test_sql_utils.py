import unittest
import os
import sys
import pandas as pd

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.sql_utils import is_sql_query, extract_table_name_from_sql, format_sql_label
from src.message_manager import MessageManager
from src.test_config import TEST_INIT_SQL, reset_test_database, TestDatabase

class TestSQLUtils(unittest.TestCase):
    def setUp(self):
        """Set up a fresh test database before each test"""
        # Reset the test database
        reset_test_database()
        
        # Create a fresh database instance
        self.db = TestDatabase()
        
        # Create a message manager instance
        self.message_manager = MessageManager()
        self.message_manager.db = self.db  # Use the test database
        
        # Initialize with test data
        for sql in TEST_INIT_SQL:
            self.db.execute_query(sql)
    
    def tearDown(self):
        """Clean up after each test"""
        # Close database connection
        self.db.close()
    
    def test_is_sql_query(self):
        """Test SQL detection"""
        # Test SQL statements
        self.assertTrue(is_sql_query("SELECT * FROM test_table"))
        self.assertTrue(is_sql_query("select * from test_table"))
        self.assertTrue(is_sql_query("INSERT INTO test_table VALUES (1, 'test', 10.5)"))
        self.assertTrue(is_sql_query("CREATE TABLE new_table (id INT)"))
        self.assertTrue(is_sql_query("UPDATE test_table SET value = 15 WHERE id = 1"))
        self.assertTrue(is_sql_query("DELETE FROM test_table WHERE id = 1"))
        
        # Test non-SQL statements
        self.assertFalse(is_sql_query("How many records are in the test table?"))
        self.assertFalse(is_sql_query("Show me the data"))
        self.assertFalse(is_sql_query("What is the average value?"))
    
    def test_execute_sql(self):
        """Test SQL execution"""
        # Test successful query
        result, had_error, df = self.message_manager.execute_sql("SELECT * FROM test_table", self.db)
        self.assertFalse(had_error)
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 3)
        
        # Test query with error
        result, had_error, df = self.message_manager.execute_sql("SELECT * FROM nonexistent_table", self.db)
        self.assertTrue(had_error)
        self.assertIn("nonexistent_table", result)
    
    def test_extract_table_name(self):
        """Test table name extraction from SQL statements"""
        # Test CREATE TABLE
        self.assertEqual(
            extract_table_name_from_sql("CREATE TABLE new_table (id INT)"),
            "new_table"
        )
        
        # Test CREATE TABLE IF NOT EXISTS
        self.assertEqual(
            extract_table_name_from_sql("CREATE TABLE IF NOT EXISTS new_table (id INT)"),
            "new_table"
        )
        
        # Test INSERT INTO
        self.assertEqual(
            extract_table_name_from_sql("INSERT INTO test_table VALUES (1, 'test', 10.5)"),
            "test_table"
        )
        
        # Test ALTER TABLE
        self.assertEqual(
            extract_table_name_from_sql("ALTER TABLE test_table ADD COLUMN new_col TEXT"),
            "test_table"
        )
        
        # Test with schema
        self.assertEqual(
            extract_table_name_from_sql("CREATE TABLE schema.new_table (id INT)"),
            "schema.new_table"
        )
    
    def test_format_sql_label(self):
        """Test SQL label formatting"""
        # Test short query
        short_query = "SELECT * FROM test_table"
        self.assertEqual(format_sql_label(short_query), "SQL: SELECT * FROM test_table...")
        
        # Test long query
        long_query = "SELECT id, name, value FROM test_table WHERE id > 1 AND value < 30 ORDER BY name"
        self.assertTrue(len(format_sql_label(long_query)) < len(long_query))
        self.assertIn("...", format_sql_label(long_query))

if __name__ == '__main__':
    unittest.main() 