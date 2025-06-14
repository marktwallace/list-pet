import os
from typing import Optional

from .analytic_database import AnalyticDatabase
from .duckdb_analytic import DuckDBAnalytic
from .postgresql_analytic import PostgreSQLAnalytic

def create_analytic_database(
    db_type: str,
    duckdb_path: Optional[str] = None,
    postgres_conn_str: Optional[str] = None
) -> Optional[AnalyticDatabase]:
    """
    Factory function to create appropriate analytic database instance.
    
    Args:
        db_type: Type of database ("duckdb" or "postgresql")
        duckdb_path: Path to DuckDB file (required for DuckDB)
        postgres_conn_str: PostgreSQL connection string (required for PostgreSQL)
        
    Returns:
        AnalyticDatabase instance or None if creation failed
    """
    try:
        if db_type == "duckdb":
            if not duckdb_path:
                print("ERROR - DuckDB path is required for DuckDB analytic database")
                return None
            return DuckDBAnalytic(duckdb_path)
            
        elif db_type == "postgresql":
            if not postgres_conn_str:
                print("ERROR - PostgreSQL connection string is required for PostgreSQL analytic database")
                return None
            return PostgreSQLAnalytic(postgres_conn_str)
            
        else:
            print(f"ERROR - Unsupported analytic database type: {db_type}")
            return None
            
    except Exception as e:
        print(f"ERROR - Failed to create analytic database ({db_type}): {str(e)}")
        return None

def get_available_database_types() -> list[str]:
    """
    Get list of available database types based on current configuration.
    
    Returns:
        List of available database type strings
    """
    available = []
    
    # Check if PostgreSQL is available
    if os.environ.get("POSTGRES_CONN_STR"):
        available.append("postgresql")
    
    # DuckDB is always available (can create new files)
    available.append("duckdb")
    
    return available 