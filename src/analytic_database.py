from abc import ABC, abstractmethod
import pandas as pd
from typing import Union, Tuple, Optional

class AnalyticDatabase(ABC):
    """Abstract base class for analytic database operations."""
    
    @abstractmethod
    def execute_query(self, sql: str, params: Optional[list] = None) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Execute an SQL query and return results.
        
        Args:
            sql: SQL query string
            params: Optional query parameters
            
        Returns:
            Tuple of (dataframe, error_message). If successful, error_message is None.
            If failed, dataframe is None and error_message contains the error.
        """
        pass
    
    @abstractmethod
    def get_connection_info(self) -> dict:
        """
        Get information about the current database connection.
        
        Returns:
            Dict with connection details like database type, host, etc.
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> Tuple[bool, Optional[str]]:
        """
        Test if the database connection is working.
        
        Returns:
            Tuple of (success, error_message). If successful, error_message is None.
        """
        pass
    
    @abstractmethod
    def close(self):
        """Close the database connection."""
        pass 