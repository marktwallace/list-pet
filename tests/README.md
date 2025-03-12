# List Pet Tests

This directory contains integration tests for the List Pet application. The tests focus on verifying the core functionality of the application, particularly the database and SQL utilities.

## Test Structure

The tests are organized as follows:

- `test_database.py`: Tests for the Database class functionality
- `test_sql_utils.py`: Tests for SQL utility functions

## Running Tests

To run all tests, execute the following command from the project root:

```bash
python run_tests.py
```

To run a specific test file:

```bash
python -m unittest tests/test_database.py
```

To run a specific test case:

```bash
python -m unittest tests.test_database.TestDatabaseFunctionality.test_execute_query
```

## Test Database

The tests use a separate test database (`test_data/test.duckdb`) to avoid affecting the production database. This test database is reset before each test to ensure a clean testing environment.

## Adding New Tests

When adding new tests, follow these guidelines:

1. Use the `TestDatabase` class from `src/test_config.py` for database operations
2. Reset the test database before each test using `reset_test_database()`
3. Clean up resources in the `tearDown()` method
4. Add the new test class to `run_tests.py`

## Test Coverage

Current test coverage includes:

- Database operations (query execution, error handling)
- Table creation and metadata logging
- SQL query detection and parsing
- Table name extraction from SQL statements
- SQL formatting utilities

Future test coverage should include:

- Response processing
- Plot and map generation
- Message management
- AI response handling 