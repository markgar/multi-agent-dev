# Sample Test Spec: CLI Calculator

Build a simple command-line calculator application.

## Requirements

1. Accept two numbers and an operator (+, -, *, /) as command-line arguments
2. Print the result to stdout
3. Handle division by zero with a clear error message
4. Handle invalid input (non-numeric values, unknown operators) with helpful error messages
5. Support decimal numbers (not just integers)
6. Exit with code 0 on success, code 1 on error
7. Include a --help flag that shows usage instructions

## Example Usage

```
calc 10 + 5       # Output: 15
calc 3.5 * 2      # Output: 7
calc 10 / 0       # Output: Error: Division by zero
calc abc + 1      # Output: Error: Invalid number: abc
calc 10 % 5       # Output: Error: Unknown operator: %
```

## Constraints

- Single file implementation is fine
- No external dependencies beyond the standard library
- Include unit tests
