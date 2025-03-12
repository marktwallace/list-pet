import unittest
import os
import sys
import pandas as pd
from unittest.mock import patch, MagicMock, call

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.test_config import TestDatabase, reset_test_database, TEST_INIT_SQL
from src.constants import USER_ROLE, ASSISTANT_ROLE, USER_ACTOR, DATABASE_ACTOR

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
        self.mock_message_manager = MagicMock()
        self.mock_message_manager.get_messages.return_value = []
        
        # Patch the get_message_manager function in streamlit_app.py
        self.streamlit_app_patch = patch('src.streamlit_app.get_message_manager')
        self.mock_get_message_manager = self.streamlit_app_patch.start()
        self.mock_get_message_manager.return_value = self.mock_message_manager
        
        # Patch the chat engine
        self.chat_engine_patch = patch('src.chat.get_chat_engine')
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
    """Test the basic flow of a user submitting a query and getting a response"""
    def test_basic_query_flow(self):
        from src.streamlit_app import handle_user_input, generate_ai_response
        
        # 1. Set up the mock AI response
        mock_ai_response = """
        <reasoning>
        I need to query the test_table to find the record with id = 1.
        </reasoning>
        
        <sql>
        SELECT * FROM test_table WHERE id = 1
        </sql>
        
        <display>
        Here is the record with id = 1:
        - Name: Test 1
        - Value: 10.5
        </display>
        """
        self.mock_chat_engine.return_value.generate_response.return_value = mock_ai_response
        
        # 2. Simulate user input
        user_query = "Show me the record with id 1"
        
        # 3. Execute the user input handler
        should_rerun = handle_user_input(user_query, self.db)
        
        # 4. Verify the message was added to the message manager
        self.mock_message_manager.add_user_message.assert_called_once_with(user_query)
        
        # 5. Verify that the session state was updated to indicate an AI response is needed
        self.assertTrue(self.mock_session_state.needs_ai_response)
        
        # 6. Verify that the function indicated a rerun is needed
        self.assertTrue(should_rerun)
        
        # 7. Now simulate the AI response generation
        generate_ai_response(self.mock_chat_engine.return_value, self.db)
        
        # 8. Verify the chat engine was called with the messages
        self.mock_chat_engine.return_value.generate_response.assert_called_once()
        
        # 9. Verify the AI response was added to the message manager
        self.mock_message_manager.add_assistant_message.assert_called_once_with(mock_ai_response)
        
        # 10. Verify that SQL was executed
        # The SQL execution is handled by the handle_ai_response function, which processes the SQL blocks
        # We can verify that the database message was added, which indicates SQL was executed
        self.mock_message_manager.add_message.assert_called()
        
        # 11. Verify that the session state was updated to indicate no AI response is needed
        self.assertFalse(self.mock_session_state.needs_ai_response)

class TestSqlDirectExecution(BaseUserFlowTest):
    """Test when a user directly inputs SQL and the system executes it and displays results"""
    def test_sql_direct_execution(self):
        from src.streamlit_app import handle_user_input
        
        # 1. Simulate user input with direct SQL
        sql_query = "SELECT * FROM test_table WHERE id = 2"
        
        # 2. Execute the user input handler
        should_rerun = handle_user_input(sql_query, self.db)
        
        # 3. Verify the message was added to the message manager
        self.mock_message_manager.add_user_message.assert_called_once_with(sql_query)
        
        # 4. Verify that a database message was added with the SQL result
        # The first argument should be the database message content
        add_database_message_calls = self.mock_message_manager.add_database_message.call_args_list
        self.assertGreaterEqual(len(add_database_message_calls), 1)
        
        # 5. Verify that the first argument to add_database_message contains the SQL query
        first_call_args = add_database_message_calls[0][0]
        self.assertIn(sql_query, first_call_args[0])
        
        # 6. Verify that a dataframe was passed as the second argument
        self.assertIsInstance(first_call_args[1], pd.DataFrame)
        
        # 7. Verify that the dataframe contains the expected data
        df = first_call_args[1]
        self.assertEqual(len(df), 1)  # Should have one row
        self.assertEqual(df['id'].iloc[0], 2)  # Should be the record with id = 2
        self.assertEqual(df['name'].iloc[0], 'Test 2')  # Should have name = Test 2
        
        # 8. Verify that the function indicated a rerun is needed (this behavior has changed)
        # The implementation now sets needs_ai_response to True for all user inputs
        self.assertTrue(should_rerun)
        
        # 9. Verify that the session state was updated to indicate an AI response is needed
        self.assertTrue(self.mock_session_state.needs_ai_response)

class TestVisualizationCreation(BaseUserFlowTest):
    """Test the flow where a query results in data that is then visualized"""
    def test_visualization_creation(self):
        from src.streamlit_app import handle_user_input, generate_ai_response
        
        # 1. Set up the mock AI response with a plot specification
        mock_ai_response = """
        <reasoning>
        I'll create a bar chart of the values in the test_table.
        </reasoning>
        
        <sql>
        SELECT * FROM test_table
        </sql>
        
        <plot 
            type="bar" 
            x="name" 
            y="value" 
            title="Test Values" 
        />
        
        <display>
        Here's a bar chart showing the values for each test record.
        </display>
        """
        self.mock_chat_engine.return_value.generate_response.return_value = mock_ai_response
        
        # 2. Simulate user input
        user_query = "Show me a bar chart of the test values"
        
        # 3. Execute the user input handler
        should_rerun = handle_user_input(user_query, self.db)
        
        # 4. Verify the message was added to the message manager
        self.mock_message_manager.add_user_message.assert_called_once_with(user_query)
        
        # 5. Verify that the session state was updated to indicate an AI response is needed
        self.assertTrue(self.mock_session_state.needs_ai_response)
        
        # 6. Verify that the function indicated a rerun is needed
        self.assertTrue(should_rerun)
        
        # 7. Now simulate the AI response generation
        generate_ai_response(self.mock_chat_engine.return_value, self.db)
        
        # 8. Verify the AI response was added to the message manager
        self.mock_message_manager.add_assistant_message.assert_called_once_with(mock_ai_response)
        
        # 9. Verify that SQL was executed
        # We can verify that the database message was added, which indicates SQL was executed
        self.mock_message_manager.add_message.assert_called()
        
        # 10. Verify that a plot message was added
        # This is a bit tricky to test directly, so we'll check that add_plot_message was called
        self.mock_message_manager.add_plot_message.assert_called()
        
        # 11. Verify that the session state was updated to indicate no AI response is needed
        self.assertFalse(self.mock_session_state.needs_ai_response)

class TestErrorHandlingFlow(BaseUserFlowTest):
    """Test how the system handles and recovers from errors"""
    def test_error_handling_flow(self):
        from src.streamlit_app import handle_user_input, generate_ai_response
        
        # 1. Set up the mock AI response with an error
        mock_ai_response = """
        <reasoning>
        I'll query the nonexistent_table to get the data.
        </reasoning>
        
        <sql>
        SELECT * FROM nonexistent_table
        </sql>
        
        <display>
        Here are the results from the nonexistent_table.
        </display>
        """
        
        # Set up a second response that the system will generate after encountering an error
        mock_recovery_response = """
        <reasoning>
        I apologize for the error. It seems the table doesn't exist. Let me query the test_table instead.
        </reasoning>
        
        <sql>
        SELECT * FROM test_table
        </sql>
        
        <display>
        Here are the results from the test_table.
        </display>
        """
        
        # Configure the mock to return different responses on successive calls
        self.mock_chat_engine.return_value.generate_response.side_effect = [
            mock_ai_response,
            mock_recovery_response
        ]
        
        # 2. Simulate user input
        user_query = "Show me data from the nonexistent table"
        
        # 3. Execute the user input handler
        should_rerun = handle_user_input(user_query, self.db)
        
        # 4. Verify the message was added to the message manager
        self.mock_message_manager.add_user_message.assert_called_once_with(user_query)
        
        # 5. Verify that the session state was updated to indicate an AI response is needed
        self.assertTrue(self.mock_session_state.needs_ai_response)
        
        # 6. Verify that the function indicated a rerun is needed
        self.assertTrue(should_rerun)
        
        # 7. Now simulate the AI response generation
        generate_ai_response(self.mock_chat_engine.return_value, self.db)
        
        # 8. Verify both AI responses were added to the message manager
        # We can't use assert_called_with because it only checks the last call
        # Instead, check that add_assistant_message was called at least twice
        self.assertGreaterEqual(self.mock_message_manager.add_assistant_message.call_count, 2)
        
        # 9. Verify that SQL was executed and an error message was added
        # The error message is added via add_message, not add_database_message
        self.mock_message_manager.add_message.assert_called()
        
        # 10. Verify that the chat engine was called a second time to generate a recovery response
        self.assertEqual(self.mock_chat_engine.return_value.generate_response.call_count, 2)
        
        # 11. Verify that the session state was updated to indicate no AI response is needed
        self.assertFalse(self.mock_session_state.needs_ai_response)

# For backward compatibility with existing tests
TestUserFlows = TestBasicQueryFlow

if __name__ == '__main__':
    unittest.main() 