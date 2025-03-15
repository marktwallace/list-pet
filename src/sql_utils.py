import re
import pandas as pd
from .database import Database

def is_sql_query(text: str) -> bool:
    """Check if text is SQL (either explicit <sql> tag or common SQL patterns)."""
    text = text.strip()
    return text.startswith("<sql>") or bool(re.match(
        r"^\s*(?:"
        r"SELECT\s+(?:\w+|\*)|"
        r"CREATE\s+(?:TABLE|DATABASE|VIEW|INDEX)|"
        r"DROP\s+(?:TABLE|DATABASE|VIEW|INDEX)|"
        r"ALTER\s+(?:TABLE|DATABASE|VIEW)|"
        r"INSERT\s+INTO|"
        r"DELETE\s+FROM|"
        r"UPDATE\s+\w+|"
        r"SHOW\s+(?:TABLES|DATABASES|COLUMNS)|"
        r"DESCRIBE\s+\w+"
        r")\s*.*",
        text, re.IGNORECASE
    ))

def format_sql_label(sql: str, max_length: int = 45) -> str:
    """Format SQL query into a concise label for the expander."""
    sql = sql.strip().replace('sql\n', '').strip()
    effective_length = max_length - 8
    first_line = sql.split('\n')[0].strip()
    if len(first_line) > effective_length or not first_line:
        words = sql.split()
        label = ' '.join(words[:4])
        if len(label) > effective_length:
            label = label[:effective_length]
    else:
        label = first_line[:effective_length]
    return f"SQL: {label}..."

def extract_table_name_from_sql(sql: str) -> str:
    """Extract table name from SQL query.
    
    Supports:
    - CREATE TABLE [IF NOT EXISTS] table_name
    - ALTER TABLE table_name
    - DROP TABLE [IF EXISTS] table_name
    - INSERT INTO table_name
    """
    sql = sql.strip()
    
    # CREATE TABLE [IF NOT EXISTS] table_name
    if sql.upper().startswith("CREATE TABLE"):
        match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
        if match:
            return match.group(1)
    
    # ALTER TABLE table_name
    elif sql.upper().startswith("ALTER TABLE"):
        match = re.search(r"ALTER\s+TABLE\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
        if match:
            return match.group(1)
    
    # DROP TABLE [IF EXISTS] table_name
    elif sql.upper().startswith("DROP TABLE"):
        match = re.search(r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
        if match:
            return match.group(1)
    
    # INSERT INTO table_name
    elif sql.upper().startswith("INSERT INTO"):
        match = re.search(r"INSERT\s+INTO\s+(\w+(?:\.\w+)?)", sql, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return ""

def is_command(text: str) -> bool:
    """Check if text is a command (starts with /)."""
    return text.strip().startswith("/")

def handle_command(command: str) -> str:
    """Handle a command and return the result."""
    command = command.strip()
    
    if command.startswith("/help"):
        return """
Available commands:
/help - Show this help message
/tables - List all tables
/schema <table_name> - Show schema for a table
/count <table_name> - Count rows in a table
/sample <table_name> [limit] - Show sample rows from a table
"""
    
    elif command.startswith("/tables"):
        db = Database()
        tables = db.get_tables()
        if not tables:
            return "No tables found in the database."
        return "Tables in the database:\n" + "\n".join(f"- {table}" for table in tables)
    
    elif command.startswith("/schema"):
        parts = command.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /schema <table_name>"
        
        table_name = parts[1].strip()
        db = Database()
        schema = db.get_table_schema(table_name)
        
        if not schema:
            return f"Table '{table_name}' not found or has no columns."
        
        result = f"Schema for table '{table_name}':\n"
        for col in schema:
            result += f"- {col['name']} ({col['type']})"
            if col.get('pk'):
                result += " PRIMARY KEY"
            if col.get('notnull'):
                result += " NOT NULL"
            result += "\n"
        
        return result
    
    elif command.startswith("/count"):
        parts = command.split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /count <table_name>"
        
        table_name = parts[1].strip()
        db = Database()
        try:
            count = db.get_table_row_count(table_name)
            return f"Table '{table_name}' has {count} rows."
        except Exception as e:
            return f"Error counting rows in '{table_name}': {str(e)}"
    
    elif command.startswith("/sample"):
        parts = command.split(maxsplit=2)
        if len(parts) < 2:
            return "Usage: /sample <table_name> [limit]"
        
        table_name = parts[1].strip()
        limit = 5  # Default limit
        
        if len(parts) >= 3:
            try:
                limit = int(parts[2])
            except ValueError:
                return f"Invalid limit: {parts[2]}. Please provide a number."
        
        db = Database()
        try:
            df, error = db.execute_query(f"SELECT * FROM {table_name} LIMIT {limit}")
            if error:
                return f"Error sampling '{table_name}': {error}"
            
            if df is None or df.empty:
                return f"No data found in table '{table_name}'."
            
            # Format as a simple text table
            result = f"Sample data from '{table_name}' (limit {limit}):\n\n"
            
            # Add header
            result += " | ".join(str(col) for col in df.columns) + "\n"
            result += "-" * (sum(len(str(col)) for col in df.columns) + 3 * (len(df.columns) - 1)) + "\n"
            
            # Add rows
            for _, row in df.iterrows():
                result += " | ".join(str(val) for val in row) + "\n"
            
            return result
        except Exception as e:
            return f"Error sampling '{table_name}': {str(e)}"
    
    else:
        return f"Unknown command: {command}. Type /help for available commands." 