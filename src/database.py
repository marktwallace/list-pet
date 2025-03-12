import duckdb
import streamlit as st
import pandas as pd
import os
import traceback

@st.cache_resource
def get_database():
    """Get or create database connection"""
    os.makedirs("db", exist_ok=True)
    return Database()

class Database:
    def __init__(self):
        try:
            self.conn = duckdb.connect('db/list_pet.db')
            print("DEBUG - Database connection established successfully")
        except Exception as e:
            error_msg = f"Failed to connect to database: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - Database connection traceback: {traceback.format_exc()}")
            # Re-raise to prevent app from starting with a broken database connection
            raise RuntimeError(f"Database connection failed: {str(e)}. Please check if the database file is accessible.")
    
    def execute_query(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)"""
        try:
            result = self.conn.execute(sql)
            
            # If it's a SELECT or SHOW statement and returns data, return the dataframe
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
                try:
                    df = result.df()
                    if not df.empty:
                        print(f"DEBUG - Query returned {len(df)} rows with columns: {df.columns.tolist()}")
                        return df, None
                    else:
                        message = "Query returned no rows."
                        print(f"DEBUG - {message}")
                        return None, message
                except Exception as e:
                    error_msg = f"Error displaying results: {str(e)}"
                    print(f"ERROR - {error_msg}")
                    print(f"ERROR - Result display traceback: {traceback.format_exc()}")
                    return None, error_msg
            else:
                # For non-SELECT statements, provide information about the operation
                # But don't treat these as errors for internal processing
                if sql.strip().upper().startswith("INSERT"):
                    return None, "INSERT operation completed."
                elif sql.strip().upper().startswith("UPDATE"):
                    message = "UPDATE operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                elif sql.strip().upper().startswith("DELETE"):
                    message = "DELETE operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                elif sql.strip().upper().startswith("CREATE"):
                    # For CREATE statements, return None for the error message
                    # This allows metadata initialization to work correctly
                    print("DEBUG - CREATE operation completed successfully")
                    return None, None
                elif sql.strip().upper().startswith("DROP"):
                    message = "DROP operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                elif sql.strip().upper().startswith("ALTER"):
                    message = "ALTER operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                else:
                    message = "Operation completed."
                    print(f"DEBUG - {message}")
                    return None, message
                    
        except Exception as e:
            error_msg = f"SQL Error: {str(e)}"
            print(f"ERROR - {error_msg}")
            print(f"ERROR - SQL execution traceback: {traceback.format_exc()}")
            
            # Provide more specific guidance based on the error type
            if "no such table" in str(e).lower():
                error_msg += "\n\nThe table you're trying to query doesn't exist. Use SHOW TABLES to see available tables or CREATE TABLE to create a new one."
            elif "syntax error" in str(e).lower():
                error_msg += "\n\nThere's a syntax error in your SQL query. Please check your query syntax and try again."
            elif "not found" in str(e).lower() and "column" in str(e).lower():
                error_msg += "\n\nOne or more columns in your query don't exist in the table. Use DESCRIBE [table_name] to see available columns."
            elif "constraint" in str(e).lower() and "violation" in str(e).lower():
                error_msg += "\n\nYour query violates a constraint (like a unique key or foreign key). Please check your data and try again."
            
            return None, error_msg 