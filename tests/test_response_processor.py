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

class TestResponseProcessor(unittest.TestCase):
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
    
    def test_process_sql_blocks_success(self):
        """Test processing SQL blocks with successful queries"""
        # Create a parsed response with SQL blocks
        parsed = {
            "sql": [
                {"query": "SELECT * FROM test_table WHERE id = 1"}
            ]
        }
        
        # Process the SQL blocks
        sql_messages, had_error, last_df = process_sql_blocks(parsed, self.db)
        
        # Verify results
        self.assertFalse(had_error)
        self.assertIsNotNone(last_df)
        self.assertEqual(len(sql_messages), 1)
        self.assertIn("dataframe", sql_messages[0])
        self.assertEqual(sql_messages[0]["role"], USER_ROLE)
        self.assertIn(DATABASE_ACTOR, sql_messages[0]["content"])
        
        # Verify dataframe content
        self.assertEqual(len(last_df), 1)
        self.assertEqual(last_df["id"].iloc[0], 1)
        self.assertEqual(last_df["name"].iloc[0], "Test 1")
    
    def test_process_sql_blocks_error(self):
        """Test processing SQL blocks with error queries"""
        # Create a parsed response with SQL blocks containing an error
        parsed = {
            "sql": [
                {"query": "SELECT * FROM nonexistent_table"}
            ]
        }
        
        # Process the SQL blocks
        sql_messages, had_error, last_df = process_sql_blocks(parsed, self.db)
        
        # Verify results
        self.assertTrue(had_error)
        self.assertIsNone(last_df)
        self.assertEqual(len(sql_messages), 1)
        self.assertEqual(sql_messages[0]["role"], USER_ROLE)
        self.assertIn(DATABASE_ACTOR, sql_messages[0]["content"])
        self.assertIn("nonexistent_table", sql_messages[0]["content"])
    
    def test_process_sql_blocks_multiple(self):
        """Test processing multiple SQL blocks"""
        # Create a parsed response with multiple SQL blocks
        parsed = {
            "sql": [
                {"query": "SELECT * FROM test_table WHERE id = 1"},
                {"query": "SELECT * FROM test_table WHERE id = 2"}
            ]
        }
        
        # Process the SQL blocks
        sql_messages, had_error, last_df = process_sql_blocks(parsed, self.db)
        
        # Verify results
        self.assertFalse(had_error)
        self.assertIsNotNone(last_df)
        self.assertEqual(len(sql_messages), 2)
        
        # Verify last dataframe is from the second query
        self.assertEqual(len(last_df), 1)
        self.assertEqual(last_df["id"].iloc[0], 2)
        self.assertEqual(last_df["name"].iloc[0], "Test 2")
    
    def test_process_sql_blocks_mixed_results(self):
        """Test processing SQL blocks with mixed success and error results"""
        # Create a parsed response with mixed SQL blocks
        parsed = {
            "sql": [
                {"query": "SELECT * FROM test_table WHERE id = 1"},
                {"query": "SELECT * FROM nonexistent_table"},
                {"query": "SELECT * FROM test_table WHERE id = 3"}
            ]
        }
        
        # Process the SQL blocks
        sql_messages, had_error, last_df = process_sql_blocks(parsed, self.db)
        
        # Verify results
        self.assertTrue(had_error)  # Should be True because one query had an error
        self.assertIsNotNone(last_df)  # Should still have a dataframe from the last successful query
        self.assertEqual(len(sql_messages), 3)
        
        # Verify last dataframe is from the third query
        self.assertEqual(len(last_df), 1)
        self.assertEqual(last_df["id"].iloc[0], 3)
        self.assertEqual(last_df["name"].iloc[0], "Test 3")
    
    def test_prepare_plot_error_message(self):
        """Test preparing plot error messages"""
        # Create a sample plot specification
        plot_spec = {
            "type": "bar",
            "x": "nonexistent_column",
            "y": "value",
            "title": "Test Plot"
        }
        
        # Create a sample dataframe
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["Test 1", "Test 2", "Test 3"],
            "value": [10.5, 20.1, 30.7]
        })
        
        # Prepare an error message
        error_message = "Column 'nonexistent_column' not found in dataframe"
        error_msg = prepare_plot_error_message(plot_spec, error_message, df)
        
        # Verify the error message
        self.assertEqual(error_msg["role"], USER_ROLE)
        self.assertIn(DATABASE_ACTOR, error_msg["content"])
        self.assertIn("Error creating bar plot", error_msg["content"])
        self.assertIn(error_message, error_msg["content"])
        self.assertIn("Available columns", error_msg["content"])
        self.assertIn("id", error_msg["content"])
        self.assertIn("name", error_msg["content"])
        self.assertIn("value", error_msg["content"])
        self.assertIn(json.dumps(plot_spec, indent=2), error_msg["content"])
        self.assertIs(error_msg["dataframe"], df)
    
    def test_prepare_map_error_message(self):
        """Test preparing map error messages"""
        # Create a sample map specification
        map_spec = {
            "type": "scatter_geo",
            "lat": "nonexistent_lat",
            "lon": "nonexistent_lon",
            "title": "Test Map"
        }
        
        # Create a sample dataframe
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "city": ["New York", "Los Angeles", "Chicago"],
            "latitude": [40.7128, 34.0522, 41.8781],
            "longitude": [-74.0060, -118.2437, -87.6298]
        })
        
        # Prepare an error message
        error_message = "Columns 'nonexistent_lat' and 'nonexistent_lon' not found in dataframe"
        error_msg = prepare_map_error_message(map_spec, error_message, df)
        
        # Verify the error message
        self.assertEqual(error_msg["role"], USER_ROLE)
        self.assertIn(DATABASE_ACTOR, error_msg["content"])
        self.assertIn("Error creating scatter_geo map", error_msg["content"])
        self.assertIn(error_message, error_msg["content"])
        self.assertIn("Available columns", error_msg["content"])
        self.assertIn("id", error_msg["content"])
        self.assertIn("city", error_msg["content"])
        self.assertIn("latitude", error_msg["content"])
        self.assertIn("longitude", error_msg["content"])
        self.assertIn(json.dumps(map_spec, indent=2), error_msg["content"])
        self.assertIs(error_msg["dataframe"], df)
    
    def test_prepare_no_data_error_message(self):
        """Test preparing no data error messages"""
        # Prepare a no data error message
        error_msg = prepare_no_data_error_message()
        
        # Verify the error message
        self.assertEqual(error_msg["role"], USER_ROLE)
        self.assertIn(DATABASE_ACTOR, error_msg["content"])
        self.assertIn("No data available for visualization", error_msg["content"])
        self.assertIn("run a SELECT query", error_msg["content"])
        self.assertNotIn("dataframe", error_msg)

if __name__ == '__main__':
    unittest.main() 