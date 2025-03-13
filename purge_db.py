#!/usr/bin/env python
"""
Script to purge the database and reset it to a clean state.
Run this script before starting the application if you want to start fresh.
"""

from src.database import get_database

def main():
    print("Purging database...")
    db = get_database()
    success = db.purge_database()
    if success:
        print("Database purged successfully!")
    else:
        print("Failed to purge database. Check the logs for details.")

if __name__ == "__main__":
    main() 