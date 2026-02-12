# Sample Test Spec: Bookstore REST API

Build a REST API for a bookstore with full CRUD operations.

## Requirements

1. Create a REST API with endpoints for managing books
2. Each book has: title, author, ISBN, price, and genre
3. Support all CRUD operations: Create, Read (single + list all), Update, Delete
4. Use an in-memory or file-based database (no external database server required)
5. Validate input: title and author are required, ISBN must be unique, price must be positive
6. Return proper HTTP status codes (200, 201, 400, 404, 409, etc.)
7. Return JSON responses with consistent structure
8. Include unit/integration tests for all endpoints

## Endpoints

```
GET    /books          # List all books
GET    /books/:id      # Get a single book by ID
POST   /books          # Create a new book
PUT    /books/:id      # Update an existing book
DELETE /books/:id      # Delete a book
```

## Example Responses

### GET /books
```json
[
  {
    "id": 1,
    "title": "The Great Gatsby",
    "author": "F. Scott Fitzgerald",
    "isbn": "978-0-7432-7356-5",
    "price": 12.99,
    "genre": "Fiction"
  }
]
```

### POST /books (request body)
```json
{
  "title": "1984",
  "author": "George Orwell",
  "isbn": "978-0-451-52493-5",
  "price": 9.99,
  "genre": "Dystopian"
}
```

### Error response
```json
{
  "error": "Book not found"
}
```

## Validation Rules

- Title: required, non-empty string
- Author: required, non-empty string
- ISBN: required, must be unique across all books
- Price: required, must be a positive number
- Genre: optional string

## Constraints

- No external database server — use in-memory storage, SQLite, or equivalent
- Include tests that cover happy paths and error cases
- Seed 2-3 sample books on startup for easy manual testing
