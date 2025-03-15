import unittest
import os
import sys
import pandas as pd
from unittest.mock import patch, MagicMock, call

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.test_config import TestDatabase, reset_test_database, TEST_INIT_SQL
from src.constants import USER_ROLE, ASSISTANT_ROLE, USER_ACTOR, DATABASE_ACTOR
from src.message_manager import MessageManager

class BaseUserFlowTest(unittest.TestCase):
    """Base class for user flow tests with common setup and teardown"""
    def setUp(self):
        """Set up a fresh test database and mock components before each test"""
        # Reset the test database
        reset_test_database()
        
        # Create a fresh database instance
        self.db = TestDatabase()
        
        # Initialize with test data
        for sql in TEST_INIT_SQL:
            self.db.execute_query(sql)
        
        # Set up patches for dependencies
        # Create a real mock for the message manager
        self.mock_message_manager = MagicMock(spec=MessageManager)
        self.mock_message_manager.get_messages.return_value = []
        self.mock_message_manager.db = self.db
        
        # Patch the get_message_manager function in streamlit_app.py
        self.streamlit_app_patch = patch('src.streamlit_app.get_message_manager')
        self.mock_get_message_manager = self.streamlit_app_patch.start()
        self.mock_get_message_manager.return_value = self.mock_message_manager
        
        # Patch the chat engine
        self.chat_engine_patch = patch('src.chat.ChatEngine')
        self.mock_chat_engine = self.chat_engine_patch.start()
        self.mock_chat_engine.return_value = MagicMock()
        
        # Patch streamlit components
        self.st_patch = patch('streamlit.chat_message')
        self.mock_st = self.st_patch.start()
        self.mock_st.return_value.__enter__.return_value = MagicMock()
        
        self.st_markdown_patch = patch('streamlit.markdown')
        self.mock_st_markdown = self.st_markdown_patch.start()
        
        self.st_dataframe_patch = patch('streamlit.dataframe')
        self.mock_st_dataframe = self.st_dataframe_patch.start()
        
        self.st_plotly_chart_patch = patch('streamlit.plotly_chart')
        self.mock_st_plotly_chart = self.st_plotly_chart_patch.start()
        
        self.st_error_patch = patch('streamlit.error')
        self.mock_st_error = self.st_error_patch.start()
        
        # Create a mock session state that behaves like a dictionary but also supports attribute access
        class MockSessionState(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.needs_ai_response = False
                
            def __getattr__(self, key):
                if key in self:
                    return self[key]
                return getattr(super(), key)
                
            def __setattr__(self, key, value):
                self[key] = value
        
        self.mock_session_state = MockSessionState()
        self.st_session_state_patch = patch('streamlit.session_state', self.mock_session_state)
        self.st_session_state_patch.start()
    
    def tearDown(self):
        """Clean up after each test"""
        # Close database connection
        self.db.close()
        
        # Stop all patches
        self.streamlit_app_patch.stop()
        self.chat_engine_patch.stop()
        self.st_patch.stop()
        self.st_markdown_patch.stop()
        self.st_dataframe_patch.stop()
        self.st_plotly_chart_patch.stop()
        self.st_error_patch.stop()
        self.st_session_state_patch.stop()

class TestBasicQueryFlow(BaseUserFlowTest):
    """Test basic query flow where user asks a question and gets a response"""
    
    def test_basic_query_flow(self):
        """Test basic query flow with a simple question"""
        # Import here to avoid circular imports
        from src.streamlit_app import handle_user_input, handle_ai_response
        
        # Set up the mock message manager to return appropriate responses
        self.mock_message_manager.execute_sql.return_value = (
            "Result: Data from test_table", 
            False, 
            pd.DataFrame({
                "id": [1, 2, 3],
                "name": ["Test 1", "Test 2", "Test 3"],
                "value": [10.5, 20.1, 30.7]
            })
        )
        
        # Set up the mock chat engine to return a response with SQL
        mock_response = """
        Here's the data from the test table:
        
        ```sql
        SELECT * FROM test_table
        ```
        """
        self.mock_chat_engine.return_value.generate_response.return_value = mock_response
        
        # Simulate user input
        user_query = "Show me the data in the test table"
        
        # Call the function under test
        should_rerun = handle_user_input(user_query)
        
        # Verify the message manager was called correctly
        self.mock_message_manager.add_user_message.assert_called_once_with(user_query)
        
        # Verify that the function returns False since this is not an SQL query or command
        self.assertFalse(should_rerun)
        
        # Now simulate the AI response
        handle_ai_response(mock_response, self.mock_chat_engine.return_value, self.db)
        
        # Verify the message manager was called to add the assistant message
        self.mock_message_manager.add_assistant_message.assert_called_once()
        
        # Verify SQL was executed
        self.mock_message_manager.execute_sql.assert_called_once_with("SELECT * FROM test_table")
        
        # Verify database message was added with the result
        self.mock_message_manager.add_database_message.assert_called_once()

class TestSqlDirectExecution(BaseUserFlowTest):
    """Test direct SQL execution flow where user enters SQL directly"""
    
    def test_sql_direct_execution(self):
        """Test direct SQL execution flow"""
        # Import here to avoid circular imports
        from src.streamlit_app import handle_user_input
        
        # Set up the mock message manager to return appropriate responses
        self.mock_message_manager.execute_sql.return_value = (
            "Result: Data from test_table", 
            False, 
            pd.DataFrame({
                "id": [1, 2, 3],
                "name": ["Test 1", "Test 2", "Test 3"],
                "value": [10.5, 20.1, 30.7]
            })
        )
        
        # Simulate user input with direct SQL
        sql_query = "SELECT * FROM test_table"
        
        # Call the function under test
        should_rerun = handle_user_input(sql_query)
        
        # Verify the message manager was called correctly
        self.mock_message_manager.add_user_message.assert_called_once_with(sql_query)
        
        # Verify SQL was executed
        self.mock_message_manager.execute_sql.assert_called_once_with(sql_query)
        
        # Verify database message was added with the result
        self.mock_message_manager.add_database_message.assert_called_once()
        
        # Verify that the function returns True since this is an SQL query
        self.assertTrue(should_rerun)

class TestVisualizationCreation(BaseUserFlowTest):
    """Test visualization creation flow where AI creates a plot or map"""
    
    def test_visualization_creation(self):
        """Test visualization creation flow"""
        # Import here to avoid circular imports
        from src.streamlit_app import handle_user_input, handle_ai_response
        
        # Create a sample dataframe
        df = pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["Test 1", "Test 2", "Test 3"],
            "value": [10.5, 20.1, 30.7]
        })
        
        # Set up the mock message manager to return appropriate responses
        self.mock_message_manager.execute_sql.return_value = (
            "Result: Data from test_table", 
            False, 
            df
        )
        
        # Set up the mock chat engine to return a response with SQL and plot
        mock_response = """
        Here's a bar chart of the values:
        
        ```sql
        SELECT * FROM test_table
        ```
        
        <plot>
        {
            "type": "bar",
            "x": "name",
            "y": "value",
            "title": "Values by Name",
            "sql_ref": "sql_1"
        }
        </plot>
        """
        self.mock_chat_engine.return_value.generate_response.return_value = mock_response
        
        # Set up the plotter mock
        with patch('src.plotting.get_plotter') as mock_get_plotter:
            mock_plotter = MagicMock()
            mock_plotter.create_plot.return_value = (MagicMock(), None)  # (fig, error)
            mock_get_plotter.return_value = mock_plotter
            
            # Simulate user input
            user_query = "Create a bar chart of the values in the test table"
            
            # Call the function under test
            should_rerun = handle_user_input(user_query)
            
            # Verify the message manager was called correctly
            self.mock_message_manager.add_user_message.assert_called_once_with(user_query)
            
            # Verify that the function returns False since this is not an SQL query or command
            self.assertFalse(should_rerun)
            
            # Now simulate the AI response
            handle_ai_response(mock_response, self.mock_chat_engine.return_value, self.db)
            
            # Verify the message manager was called to add the assistant message
            self.mock_message_manager.add_assistant_message.assert_called_once()
            
            # Verify SQL was executed
            self.mock_message_manager.execute_sql.assert_called_once_with("SELECT * FROM test_table")
            
            # Verify database message was added with the result
            self.mock_message_manager.add_database_message.assert_called_once()
            
            # Verify the plotter was called
            mock_plotter.create_plot.assert_called_once()
            
            # Verify plot message was added
            self.mock_message_manager.add_plot_message.assert_called_once()

class TestErrorHandlingFlow(BaseUserFlowTest):
    """Test error handling flow where SQL execution fails"""
    
    def test_error_handling_flow(self):
        """Test error handling flow"""
        # Import here to avoid circular imports
        from src.streamlit_app import handle_user_input, handle_ai_response
        
        # Set up the mock message manager to return an error
        self.mock_message_manager.execute_sql.return_value = (
            "SQL Error: Table 'nonexistent_table' does not exist", 
            True, 
            None
        )
        
        # Set up the mock chat engine to return a response with SQL that will fail
        mock_response = """
        Let me query that table for you:
        
        ```sql
        SELECT * FROM nonexistent_table
        ```
        """
        self.mock_chat_engine.return_value.generate_response.return_value = mock_response
        self.mock_chat_engine.return_value.generate_fallback_response.return_value = "I apologize for the error."
        
        # Simulate user input
        user_query = "Show me the data in the nonexistent table"
        
        # Call the function under test
        should_rerun = handle_user_input(user_query)
        
        # Verify the message manager was called correctly
        self.mock_message_manager.add_user_message.assert_called_once_with(user_query)
        
        # Verify that the function returns False since this is not an SQL query or command
        self.assertFalse(should_rerun)
        
        # Now simulate the AI response
        handle_ai_response(mock_response, self.mock_chat_engine.return_value, self.db)
        
        # Verify the message manager was called to add the assistant message
        self.mock_message_manager.add_assistant_message.assert_called_once()
        
        # Verify SQL was executed
        self.mock_message_manager.execute_sql.assert_called_once_with("SELECT * FROM nonexistent_table")
        
        # Verify database message was added with the error
        self.mock_message_manager.add_database_message.assert_called_once()

# For backward compatibility with existing tests
TestUserFlows = TestBasicQueryFlow

if __name__ == '__main__':
    unittest.main() 