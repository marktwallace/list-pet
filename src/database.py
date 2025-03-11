import duckdb
import streamlit as st
import pandas as pd
import os

@st.cache_resource
def get_database():
    """Get or create database connection"""
    os.makedirs("db", exist_ok=True)
    return Database()

class Database:
    def __init__(self):
        self.conn = duckdb.connect('db/list_pet.db')
    
    def execute_query(self, sql: str) -> tuple[pd.DataFrame | None, str | None]:
        """Execute SQL and return (dataframe, error_message)"""
        try:
            result = self.conn.execute(sql)
            
            # If it's a SELECT or SHOW statement and returns data, return the dataframe
            if sql.strip().upper().startswith(("SELECT", "SHOW", "DESCRIBE")):
                try:
                    df = result.df()
                    if not df.empty:
                        return df, None
                    else:
                        return None, "Query returned no rows"
                except Exception as e:
                    return None, f"Error displaying results: {str(e)}"
            else:
                # For non-SELECT statements, provide information about the operation
                # But don't treat these as errors for internal processing
                if sql.strip().upper().startswith("INSERT"):
                    return None, "INSERT operation completed. No data to display. Use SELECT to view data."
                elif sql.strip().upper().startswith("UPDATE"):
                    return None, "UPDATE operation completed. No data to display. Use SELECT to view data."
                elif sql.strip().upper().startswith("DELETE"):
                    return None, "DELETE operation completed. No data to display. Use SELECT to view data."
                elif sql.strip().upper().startswith("CREATE"):
                    # For CREATE statements, return None for the error message
                    # This allows metadata initialization to work correctly
                    return None, None
                elif sql.strip().upper().startswith("DROP"):
                    return None, "DROP operation completed. No data to display. Use SELECT to view data."
                elif sql.strip().upper().startswith("ALTER"):
                    return None, "ALTER operation completed. No data to display. Use SELECT to view data."
                else:
                    return None, "Operation completed. No data to display. Use SELECT to view data."
                    
        except Exception as e:
            return None, f"SQL Error: {str(e)}" 