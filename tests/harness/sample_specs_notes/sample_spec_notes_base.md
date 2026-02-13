# Notes App — Base

A minimal full-stack notes application.

## Backend

- ASP.NET Core minimal API (C#)
- In-memory list storage (no database)
- `GET /notes` — returns all notes as JSON array
- `POST /notes` — accepts `{ "text": "..." }`, assigns an auto-increment `id`, returns the created note
- `GET /health` — returns `{ "status": "ok" }`
- Serve the React frontend's build output as static files from the root route

## Frontend

- React app (create with Vite)
- Single page that shows a list of notes (fetched from `GET /notes`)
- A text input and "Add" button to create a new note via `POST /notes`
- After adding, refresh the list
- Minimal styling — just enough to be readable
