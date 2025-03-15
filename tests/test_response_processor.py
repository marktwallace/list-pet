import unittest
import os
import sys
import pandas as pd
import json
from unittest.mock import MagicMock, patch

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.response_processor import (
    process_sql_blocks,
    prepare_plot_error_message,
    prepare_map_error_message,
    prepare_no_data_error_message
)
from src.constants import USER_ROLE, DATABASE_ACTOR
from src.test_config import TestDatabase, reset_test_database, TEST_INIT_SQL
from src.message_manager import MessageManager

class TestResponseProcessor(unittest.TestCase):
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
    
    def test_process_sql_blocks_success(self):
        """Test processing SQL blocks with successful queries"""
        # Create a response with SQL blocks
        response = """
        Here's a query to get data from the test table:
        
        ```sql
        SELECT * FROM test_table WHERE id = 1
        ```
        """
        
        # Process the SQL blocks
        parsed_response, sql_blocks = process_sql_blocks(response)
        
        # Verify results
        self.assertIsInstance(parsed_response, str)
        self.assertIsInstance(sql_blocks, list)
        self.assertEqual(len(sql_blocks), 1)
        self.assertEqual(sql_blocks[0]["sql"], "SELECT * FROM test_table WHERE id = 1")
        
        # Execute the SQL to verify it works
        for block in sql_blocks:
            result, is_error, df = self.message_manager.execute_sql(block["sql"])
            self.assertFalse(is_error)
            self.assertIsNotNone(df)
    
    def test_process_sql_blocks_error(self):
        """Test processing SQL blocks with error queries"""
        # Create a response with SQL blocks that will cause errors
        response = """
        Here's a query that will cause an error:
        
        ```sql
        SELECT * FROM nonexistent_table
        ```
        """
        
        # Process the SQL blocks
        parsed_response, sql_blocks = process_sql_blocks(response)
        
        # Verify results
        self.assertIsInstance(parsed_response, str)
        self.assertIsInstance(sql_blocks, list)
        self.assertEqual(len(sql_blocks), 1)
        self.assertEqual(sql_blocks[0]["sql"], "SELECT * FROM nonexistent_table")
        
        # Execute the SQL to verify it produces an error
        for block in sql_blocks:
            result, is_error, df = self.message_manager.execute_sql(block["sql"])
            self.assertTrue(is_error)
            self.assertIn("nonexistent_table", result)
    
    def test_process_sql_blocks_multiple(self):
        """Test processing multiple SQL blocks"""
        # Create a response with multiple SQL blocks
        response = """
        Here are multiple queries:
        
        ```sql
        SELECT * FROM test_table WHERE id = 1
        ```
        
        And another one:
        
        ```sql
        SELECT * FROM test_table WHERE id = 2
        ```
        """
        
        # Process the SQL blocks
        parsed_response, sql_blocks = process_sql_blocks(response)
        
        # Verify results
        self.assertIsInstance(parsed_response, str)
        self.assertIsInstance(sql_blocks, list)
        self.assertEqual(len(sql_blocks), 2)
        self.assertEqual(sql_blocks[0]["sql"], "SELECT * FROM test_table WHERE id = 1")
        self.assertEqual(sql_blocks[1]["sql"], "SELECT * FROM test_table WHERE id = 2")
    
    def test_process_sql_blocks_mixed_results(self):
        """Test processing SQL blocks with mixed success and error results"""
        # Create a response with mixed SQL blocks
        response = """
        Here's a successful query:
        
        ```sql
        SELECT * FROM test_table WHERE id = 1
        ```
        
        And here's one that will fail:
        
        ```sql
        SELECT * FROM nonexistent_table
        ```
        """
        
        # Process the SQL blocks
        parsed_response, sql_blocks = process_sql_blocks(response)
        
        # Verify results
        self.assertIsInstance(parsed_response, str)
        self.assertIsInstance(sql_blocks, list)
        self.assertEqual(len(sql_blocks), 2)
        
        # Execute the SQL to verify mixed results
        result1, is_error1, df1 = self.message_manager.execute_sql(sql_blocks[0]["sql"])
        self.assertFalse(is_error1)
        self.assertIsNotNone(df1)
        
        result2, is_error2, df2 = self.message_manager.execute_sql(sql_blocks[1]["sql"])
        self.assertTrue(is_error2)
        self.assertIn("nonexistent_table", result2)
    
    def test_prepare_plot_error_message(self):
        """Test preparing plot error messages"""
        # Create test data
        error_message = "Invalid column 'nonexistent_column'"
        
        # Call the function
        error_msg = prepare_plot_error_message(error_message)
        
        # Verify results
        self.assertIsInstance(error_msg, str)
        self.assertIn("Error creating plot", error_msg)
        self.assertIn(error_message, error_msg)
    
    def test_prepare_map_error_message(self):
        """Test preparing map error messages"""
        # Create test data
        error_message = "Invalid column 'nonexistent_column'"
        
        # Call the function
        error_msg = prepare_map_error_message(error_message)
        
        # Verify results
        self.assertIsInstance(error_msg, str)
        self.assertIn("Error creating map", error_msg)
        self.assertIn(error_message, error_msg)
    
    def test_prepare_no_data_error_message(self):
        """Test preparing no data error messages"""
        # Call the function
        error_msg = prepare_no_data_error_message()
        
        # Verify results
        self.assertIsInstance(error_msg, str)
        self.assertIn("No data available", error_msg)
        self.assertIn("visualization", error_msg)

if __name__ == '__main__':
    unittest.main() 