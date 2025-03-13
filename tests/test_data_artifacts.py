import unittest
import os
import sys
import json
import pandas as pd
from unittest.mock import patch, MagicMock

# Add the src directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from src.database import Database
from src.test_config import reset_test_database, TEST_DB_PATH

class TestDataArtifacts(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        # Reset the test database
        reset_test_database()
        
        # Create a test database instance
        with patch('src.database.duckdb.connect') as mock_connect:
            self.mock_conn = MagicMock()
            mock_connect.return_value = self.mock_conn
            self.db = Database()
            
        # Override the database connection
        self.db.conn = self.mock_conn
        
    def test_data_artifacts_table_creation(self):
        """Test that the data_artifacts table is created during initialization"""
        # Mock the execute_query method to capture calls
        with patch.object(self.db, 'execute_query') as mock_execute:
            # Call the initialization method
            self.db._initialize_pet_meta_schema()
            
            # Check if data_artifacts table creation was called
            data_artifacts_call_found = False
            for call in mock_execute.call_args_list:
                args = call[0][0]
                if "CREATE TABLE IF NOT EXISTS pet_meta.data_artifacts" in args:
                    data_artifacts_call_found = True
                    break
            
            self.assertTrue(data_artifacts_call_found, "data_artifacts table creation not found")
    
    def test_log_data_artifact(self):
        """Test logging a data artifact"""
        # Create a mock dataframe
        df = pd.DataFrame({'col1': [1, 2, 3], 'col2': ['a', 'b', 'c']})
        
        # Create a mock message with a dataframe
        message = {
            "role": "user",
            "content": "Database:\nQuery executed successfully",
            "dataframe": df,
            "query_text": "SELECT * FROM test_table"
        }
        
        # Mock the execute_query method
        with patch.object(self.db, 'execute_query') as mock_execute:
            # Call the log_data_artifact method
            result = self.db.log_data_artifact(1, message)
            
            # Check if the method was called with the correct parameters
            self.assertTrue(result)
            mock_execute.assert_called_once()
            
            # Check if the SQL contains the correct values
            call_args = mock_execute.call_args[0][0]
            self.assertIn("INSERT INTO pet_meta.data_artifacts", call_args)
            self.assertIn("'dataframe'", call_args)
            
            # Check if the params were passed correctly
            if 'params' in mock_execute.call_args[1]:
                params = mock_execute.call_args[1]['params']
                self.assertEqual(params[0], "SELECT * FROM test_table")
                
                # Parse the JSON metadata
                metadata = json.loads(params[1])
                self.assertIn("columns", metadata)
                self.assertEqual(metadata["columns"], ["col1", "col2"])
                self.assertEqual(metadata["shape"], [3, 2])
    
    def test_get_data_artifacts_for_message(self):
        """Test retrieving data artifacts for a message"""
        # Mock the execute_query method to return a dataframe
        mock_df = pd.DataFrame({
            'id': [1],
            'artifact_type': ['dataframe'],
            'query_text': ['SELECT * FROM test_table'],
            'metadata': ['{"columns": ["col1", "col2"], "shape": [3, 2]}']
        })
        
        with patch.object(self.db, 'execute_query', return_value=(mock_df, None)) as mock_execute:
            # Call the get_data_artifacts_for_message method
            artifacts = self.db.get_data_artifacts_for_message(1)
            
            # Check if the method was called with the correct parameters
            mock_execute.assert_called_once()
            
            # Check if the artifacts were returned correctly
            self.assertEqual(len(artifacts), 1)
            self.assertEqual(artifacts[0]["id"], 1)
            self.assertEqual(artifacts[0]["type"], "dataframe")
            self.assertEqual(artifacts[0]["query_text"], "SELECT * FROM test_table")
            self.assertEqual(artifacts[0]["metadata"]["columns"], ["col1", "col2"])
            self.assertEqual(artifacts[0]["metadata"]["shape"], [3, 2])
    
    def test_load_messages_with_artifacts(self):
        """Test loading messages with data artifacts"""
        # Mock the execute_query method to return messages with data artifacts
        mock_messages_df = pd.DataFrame({
            'id': [1, 2],
            'role': ['user', 'user'],
            'message_text': ['User: Hello', 'Database:\nQuery executed successfully'],
            'has_dataframe': [False, True],
            'has_figure': [False, False]
        })
        
        # Mock the get_data_artifacts_for_message method
        mock_artifacts = [{
            'id': 1,
            'type': 'dataframe',
            'query_text': 'SELECT * FROM test_table',
            'metadata': {'columns': ['col1', 'col2'], 'shape': [3, 2]}
        }]
        
        with patch.object(self.db, 'execute_query', return_value=(mock_messages_df, None)) as mock_execute:
            with patch.object(self.db, 'get_data_artifacts_for_message', return_value=mock_artifacts) as mock_get_artifacts:
                # Call the load_messages method
                messages = self.db.load_messages()
                
                # Check if the methods were called correctly
                mock_execute.assert_called_once()
                mock_get_artifacts.assert_called_once_with(2)  # Should be called for the second message
                
                # Check if the messages were returned correctly
                self.assertEqual(len(messages), 2)
                self.assertEqual(messages[0]["role"], "user")
                self.assertEqual(messages[0]["content"], "User: Hello")
                self.assertNotIn("had_data_artifact", messages[0])
                
                self.assertEqual(messages[1]["role"], "user")
                self.assertEqual(messages[1]["content"], "Database:\nQuery executed successfully")
                self.assertTrue(messages[1]["had_data_artifact"])
                self.assertEqual(messages[1]["message_id"], 2)
                self.assertEqual(messages[1]["data_artifacts"], mock_artifacts)

if __name__ == '__main__':
    unittest.main() 