#!/usr/bin/env python3
import unittest
import sys
import os

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Import test classes
from tests.test_database import TestDatabaseOperations
from tests.test_sql_utils import TestSQLUtils
from tests.test_response_processor import TestResponseProcessor
from tests.test_ai_patterns import TestAIPatterns
from tests.test_user_flows import (
    TestBasicQueryFlow, 
    TestSqlDirectExecution, 
    TestVisualizationCreation, 
    TestErrorHandlingFlow
)

def run_tests():
    """Run all tests and return success status"""
    # Create a test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases to the suite
    test_suite.addTest(unittest.makeSuite(TestDatabaseOperations))
    test_suite.addTest(unittest.makeSuite(TestSQLUtils))
    test_suite.addTest(unittest.makeSuite(TestResponseProcessor))
    test_suite.addTest(unittest.makeSuite(TestAIPatterns))
    test_suite.addTest(unittest.makeSuite(TestBasicQueryFlow))
    test_suite.addTest(unittest.makeSuite(TestSqlDirectExecution))
    test_suite.addTest(unittest.makeSuite(TestVisualizationCreation))
    test_suite.addTest(unittest.makeSuite(TestErrorHandlingFlow))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Return True if successful, False otherwise
    return result.wasSuccessful()

if __name__ == '__main__':
    # Run tests and set exit code
    success = run_tests()
    sys.exit(0 if success else 1) 