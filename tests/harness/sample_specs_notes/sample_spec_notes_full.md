# Notes App — Full

A minimal full-stack notes application with create, delete, and timestamps.

## Backend

- ASP.NET Core minimal API (C#)
- In-memory list storage (no database)
- `GET /notes` — returns all notes as JSON array
- `POST /notes` — accepts `{ "text": "..." }`, assigns an auto-increment `id`, sets a `createdAt` timestamp (ISO 8601), returns the created note
- `DELETE /notes/{id}` — removes the note with the given id, returns 204 on success, 404 if not found
- `GET /health` — returns `{ "status": "ok" }`
- Serve the React frontend's build output as static files from the root route

## Frontend

- React app (create with Vite)
- Single page that shows a list of notes (fetched from `GET /notes`)
- Display the timestamp next to each note (e.g. "2 minutes ago" or a formatted date)
- A text input and "Add" button to create a new note via `POST /notes`
- A "Delete" button next to each note that calls `DELETE /notes/:id`
- After adding or deleting, refresh the list
- Minimal styling — just enough to be readable
