import re
import pandas as pd
from .database import Database

def format_sql_result(query: str, df: pd.DataFrame | None, error: str | None) -> tuple[str, pd.DataFrame | None]:
    """Format SQL results in a consistent way, returning both display text and dataframe."""
    output = []
    output.append(f"```sql\n{query}\n```")
    
    if error:
        # For actual errors, show as errors
        if error.startswith("SQL Error:"):
            output.append("Error:")
            output.append(f"```\n{error}\n```")
        # For informational messages, show as results
        else:
            output.append("Result:")
            output.append(f"```\n{error}\n```")
        return "\n".join(output), None
    elif df is not None:
        tsv_output = []
        tsv_output.append("\t".join(df.columns))
        for _, row in df.iterrows():
            tsv_output.append("\t".join(str(val) for val in row))
        
        output.append("Result:")
        output.append("```tsv\n" + "\n".join(tsv_output) + "\n```")
        return "\n".join(output), df
    else:
        # Handle case where there's no error and no dataframe
        # This happens for successful operations that don't return data
        output.append("Result:")
        
        # Determine the appropriate message based on the query type
        if query.strip().upper().startswith("CREATE"):
            output.append("```\nCREATE operation completed. No data to display.\n```")
        elif query.strip().upper().startswith("INSERT"):
            output.append("```\nINSERT operation completed. No data to display.\n```")
        elif query.strip().upper().startswith("UPDATE"):
            output.append("```\nUPDATE operation completed. No data to display.\n```")
        elif query.strip().upper().startswith("DELETE"):
            output.append("```\nDELETE operation completed. No data to display.\n```")
        elif query.strip().upper().startswith("DROP"):
            output.append("```\nDROP operation completed. No data to display.\n```")
        elif query.strip().upper().startswith("ALTER"):
            output.append("```\nALTER operation completed. No data to display.\n```")
        else:
            output.append("```\nOperation completed. No data to display.\n```")
    
    return "\n".join(output), None

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

def execute_sql(query: str, db: Database) -> tuple[str, bool, pd.DataFrame | None]:
    """Execute SQL and return (formatted_result, had_error, dataframe)."""
    df, error = db.execute_query(query)
    result, df = format_sql_result(query, df, error)
    # Only consider it an error if the error message starts with "SQL Error:"
    return result, bool(error and error.startswith("SQL Error:")), df

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