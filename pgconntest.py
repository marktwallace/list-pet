import os
import psycopg2

pg_conn_str = os.environ.get("POSTGRES_CONN_STR")
print("POSTGRES_CONN_STR", pg_conn_str)
conn = psycopg2.connect(pg_conn_str)
print("Connected!")

