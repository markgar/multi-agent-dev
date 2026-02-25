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

## Authors

### Requirements

1. Create endpoints for managing authors as a separate resource
2. Each author has: name, biography (optional), and birth year (optional)
3. Support CRUD operations: Create, Read (single + list all), Update, Delete
4. Books reference an author by author ID instead of a plain author string
5. Deleting an author is only allowed if they have no associated books (return 409 Conflict)
6. Seed 2-3 sample authors on startup; seed books should reference them

### Endpoints

```
GET    /authors          # List all authors
GET    /authors/:id      # Get a single author (include their book count)
POST   /authors          # Create a new author
PUT    /authors/:id      # Update an existing author
DELETE /authors/:id      # Delete an author (fails if books exist)
GET    /authors/:id/books  # List all books by a specific author
```

## Search and Filtering

### Requirements

1. Add a search endpoint that accepts a query string and searches across book title, author name, and ISBN
2. The book list endpoint (`GET /books`) supports optional query parameters for filtering: `genre`, `authorId`, `minPrice`, `maxPrice`
3. The book list endpoint supports sorting via `sortBy` (title, price, author) and `sortOrder` (asc, desc) query parameters
4. Filters, search, and sorting can be combined in a single request

### Endpoints

```
GET /books?genre=Fiction&minPrice=5&maxPrice=20&sortBy=price&sortOrder=asc
GET /books/search?q=gatsby
```

## Book Reviews

### Requirements

1. Users can add reviews to books
2. Each review has: reviewer name, rating (1-5 integer), comment (optional), and a created timestamp
3. Support Create, Read (list reviews for a book), and Delete operations for reviews
4. The `GET /books/:id` response includes the average rating and total review count
5. Validate that rating is an integer between 1 and 5, and reviewer name is required
6. Seed 1-2 sample reviews on the seed books at startup

### Endpoints

```
GET    /books/:id/reviews    # List all reviews for a book
POST   /books/:id/reviews    # Add a review to a book
DELETE /books/:id/reviews/:reviewId  # Delete a review
```

## Frontend: React App

### Requirements

1. Build a React single-page application using Vite as the build tool
2. Display a list of all books in a table or card layout
3. Show book details: title, author name (resolved from the author resource), ISBN, price, genre, average rating, and review count
4. Add new books via a form with validation (required fields, positive price, author selected from a dropdown of existing authors)
5. Edit existing books inline or via a modal/form
6. Delete books with a confirmation prompt
7. Show user-friendly error messages when API calls fail (e.g. duplicate ISBN, validation errors)
8. Call the backend API at the URL configured in an environment variable or config file
9. Include component tests using Vitest and React Testing Library for the book list and add/edit form
10. Include a search bar at the top of the book list that filters results as the user types (calls the search endpoint with debouncing)
11. Include filter controls for genre (dropdown), price range (min/max inputs), and author (dropdown) that update the book list
12. Display an author management page: list all authors, add new authors, edit author details, and delete authors (with an error message if they have books)
13. On the book detail view, display reviews and a form to add a new review (reviewer name, star rating selector 1-5, optional comment)

### Pages / Views

- **Book List** — main view showing all books with search bar, filter controls, and add/edit/delete actions
- **Add/Edit Book Form** — form for creating or editing a book with client-side validation and author dropdown
- **Book Detail** — detail view showing full book info, average rating, and a reviews section with an add-review form
- **Author List** — view showing all authors with book counts, and add/edit/delete actions
- **Add/Edit Author Form** — form for creating or editing an author

### UI Details

- Use plain CSS or a lightweight CSS framework (no heavy UI library required)
- Responsive layout that works on desktop and mobile
- Loading indicator while fetching data
- Empty state message when no books exist
- Client-side routing between book list, book detail, and author list views

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
