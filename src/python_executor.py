"""
Python Executor Module

This module provides functionality to execute Python code written by the LLM in a safe environment.
It handles input/output of DataFrames and can read from a MinIO-compatible object store.

Usage:
    from python_executor import execute_python_code
    
    # Create a DataFrame
    df = pd.DataFrame({'category': ['A', 'B', 'C'], 'value': [10, 20, 30]})
    
    # Define Python code - the LLM should generate code in this format
    python_code = '''
    # Read a mapping file from MinIO
    mapping = yaml.safe_load(minio.get("column_maps/categories.yaml"))
    
    # Transform the DataFrame
    df["mapped_category"] = df["category"].map(mapping)
    '''
    
    # Execute the code
    result = execute_python_code(df, python_code)
    if result.error:
        print(f"Error: {result.error}")
    else:
        # Access results
        new_df = result.dataframe  # Modified DataFrame if any
        metadata = result.metadata  # Any metadata output
"""

import re
import traceback
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd
import yaml
from io import StringIO
import sys
from textwrap import dedent

@dataclass
class ExecutionResult:
    """Container for Python code execution results"""
    dataframe: Optional[pd.DataFrame] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class MinioWrapper:
    """Wrapper for MinIO operations to provide a simplified interface"""
    def __init__(self):
        # TODO: Initialize MinIO client with credentials
        pass
        
    def get(self, path: str) -> str:
        """Get contents of a file from MinIO as a string"""
        # TODO: Implement actual MinIO get operation
        # For now, return mock data for testing
        if path == "column_maps/categories.yaml":
            return """
            A: Category A
            B: Category B
            C: Category C
            """
        raise FileNotFoundError(f"File not found: {path}")

def execute_python_code(df: Optional[pd.DataFrame], code: str) -> ExecutionResult:
    """
    Execute Python code in a safe environment with access to specific libraries and objects.
    
    Args:
        df: Optional input DataFrame
        code: Python code to execute
        
    Returns:
        ExecutionResult containing:
        - Modified DataFrame (if any)
        - Metadata dictionary (if any)
        - Error message (if execution failed)
    """
    # Create namespace with allowed objects
    namespace = {
        "pd": pd,
        "yaml": yaml,
        "minio": MinioWrapper(),
        "df": df.copy() if df is not None else None,
        "metadata": {}
    }
    
    # Capture stdout to include in metadata
    stdout = StringIO()
    sys.stdout = stdout
    
    try:
        # Clean up code indentation
        code = dedent(code.strip())
        
        # Execute the code
        exec(code, namespace)
        
        # Get stdout content
        output = stdout.getvalue().strip()
        if output:
            namespace["metadata"]["output"] = output
            
        # Return results
        return ExecutionResult(
            dataframe=namespace.get("df"),
            metadata=namespace.get("metadata"),
            error=None
        )
        
    except Exception as e:
        # Get full traceback for debugging
        tb = traceback.format_exc()
        return ExecutionResult(error=f"Error executing Python code: {str(e)}\n\nTraceback:\n{tb}")
        
    finally:
        # Restore stdout
        sys.stdout = sys.__stdout__

def main():
    """Run Python executor tests"""
    print("Running Python executor tests...\n")
    
    # Test cases
    test_cases = [
        {
            'name': "Basic DataFrame transformation",
            'df': pd.DataFrame({
                'category': ['A', 'B', 'C'],
                'value': [10, 20, 30]
            }),
            'code': """
# Map categories using YAML file
mapping = yaml.safe_load(minio.get("column_maps/categories.yaml"))
df["mapped_category"] = df["category"].map(mapping)

# Add some metadata
metadata["changes"] = ["Added mapped_category column"]
""",
            'should_succeed': True
        },
        {
            'name': "Print output capture",
            'df': None,
            'code': """
print("This is a test message")
metadata["custom"] = "value"
""",
            'should_succeed': True
        },
        {
            'name': "Invalid code",
            'df': None,
            'code': """
this is not valid python code
""",
            'should_succeed': False
        },
        {
            'name': "Missing column reference",
            'df': pd.DataFrame({'A': [1, 2, 3]}),
            'code': """
df["B"] = df["nonexistent_column"] * 2
""",
            'should_succeed': False
        }
    ]
    
    # Run tests
    for test in test_cases:
        print(f"Test: {test['name']}")
        result = execute_python_code(test['df'], test['code'])
        
        if test['should_succeed']:
            if result.error:
                print(f"✗ Failed: {result.error}")
            else:
                print("✓ Success")
                if result.dataframe is not None:
                    print(f"DataFrame:\n{result.dataframe}")
                if result.metadata:
                    print(f"Metadata: {result.metadata}")
        else:
            print("✓ Success" if result.error else "✗ Error: Expected error but got success")
        print()

if __name__ == "__main__":
    main() 