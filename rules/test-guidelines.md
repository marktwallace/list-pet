# List Pet Testing Guidelines

## Testing Strategy

1. **Integration Testing Focus**: We prioritize integration tests over unit tests to verify that components work together correctly.

2. **Test Database**: All tests use a separate test database (`test_data/test.duckdb`) that resets between test runs.

3. **Minimal Mocking**: We minimize mocks and prefer testing with real components when possible.

4. **Critical Flows**: Tests focus on critical user flows rather than exhaustive coverage of edge cases.

5. **AI Component Testing**: For AI components, we use deterministic settings (temperature=0, top_p=0) and focus on testing structured output patterns like SQL, plot, and map blocks.

## Test Categories

1. **Database Tests**: Verify database operations, table creation, and metadata logging.

2. **SQL Utility Tests**: Verify SQL detection, execution, and parsing functions.

3. **Response Processing Tests**: Verify handling of AI responses and extraction of structured blocks.

4. **AI Pattern Tests**: Verify parsing of AI response patterns (SQL, plot, map blocks).

5. **User Flow Tests**: Verify end-to-end user interactions.

## Test Implementation Guidelines

1. Always reset the test database before each test using `reset_test_database()`.

2. Clean up resources in the `tearDown()` method.

3. Use the `TestDatabase` class from `src/test_config.py` for database operations.

4. Focus tests on verifying functionality that users directly interact with.

5. Keep tests independent and avoid dependencies between test cases.

## Running Tests

### Preferred Method (using run_tests.py)

```bash
# Run all tests
python run_tests.py

# The run_tests.py script automatically:
# - Sets up the correct Python path
# - Runs all test suites in the correct order
# - Returns appropriate exit code (0 for success, 1 for failure)
```

### Alternative Methods

```bash
# Run all tests using unittest discover
python -m unittest discover -s tests

# Run a specific test file
python -m unittest tests/test_database.py

# Run a specific test case
python -m unittest tests.test_database.TestDatabaseOperations.test_execute_query
```

## Adding New Tests

When adding new test classes:

1. Create a new test file in the `tests` directory
2. Import the test class in `run_tests.py`
3. Add the test class to the test suite in the `run_tests()` function 