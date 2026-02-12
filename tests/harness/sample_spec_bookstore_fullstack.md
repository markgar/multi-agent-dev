# Sample Test Spec: Bookstore Full-Stack App

Build a full-stack bookstore application with a .NET REST API backend and a React frontend.

## Backend: REST API

### Requirements

1. Create a REST API with endpoints for managing books
2. Each book has: title, author, ISBN, price, and genre
3. Support all CRUD operations: Create, Read (single + list all), Update, Delete
4. Use in-memory storage (no external database server required)
5. Validate input: title and author are required, ISBN must be unique, price must be positive
6. Return proper HTTP status codes (200, 201, 400, 404, 409, etc.)
7. Return JSON responses with consistent error structure: `{"error": "..."}`
8. Enable CORS so the React frontend can call the API
9. Seed 2-3 sample books on startup for easy manual testing
10. Include integration tests covering happy paths and error cases for all endpoints

### Endpoints

```
GET    /books          # List all books
GET    /books/:id      # Get a single book by ID
POST   /books          # Create a new book
PUT    /books/:id      # Update an existing book
DELETE /books/:id      # Delete a book
```

### Example Responses

#### GET /books
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

#### POST /books (request body)
```json
{
  "title": "1984",
  "author": "George Orwell",
  "isbn": "978-0-451-52493-5",
  "price": 9.99,
  "genre": "Dystopian"
}
```

#### Error response
```json
{
  "error": "Book not found"
}
```

### Validation Rules

- Title: required, non-empty string
- Author: required, non-empty string
- ISBN: required, must be unique across all books
- Price: required, must be a positive number
- Genre: optional string

## Frontend: React App

### Requirements

1. Build a React single-page application using Vite as the build tool
2. Display a list of all books in a table or card layout
3. Show book details: title, author, ISBN, price, and genre
4. Add new books via a form with validation (required fields, positive price)
5. Edit existing books inline or via a modal/form
6. Delete books with a confirmation prompt
7. Show user-friendly error messages when API calls fail (e.g. duplicate ISBN, validation errors)
8. Call the backend API at the URL configured in an environment variable or config file
9. Include component tests using Vitest and React Testing Library for the book list and add/edit form

### Pages / Views

- **Book List** — main view showing all books with add, edit, and delete actions
- **Add/Edit Form** — form for creating or editing a book with client-side validation

### UI Details

- Use plain CSS or a lightweight CSS framework (no heavy UI library required)
- Responsive layout that works on desktop and mobile
- Loading indicator while fetching data
- Empty state message when no books exist

## Tech Stack

- **Backend:** .NET 10 (dotnet 10) with C#, minimal API
- **Frontend:** React 19 with Vite and TypeScript

## Project Structure

```
backend/          # .NET API project
frontend/         # React + Vite project
```

## Constraints

- No external database server — use in-memory storage
- Backend and frontend are separate projects in the same repo
- The frontend must be runnable with `npm install && npm run dev`
- The backend must be runnable with `dotnet run`
- Include backend integration tests covering happy paths and error cases
- Include frontend component tests using Vitest and React Testing Library
