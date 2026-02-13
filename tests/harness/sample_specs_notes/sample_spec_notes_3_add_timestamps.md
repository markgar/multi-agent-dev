# Notes App — Add Timestamps

Add created-at timestamps to the existing notes application.

## Backend

- Each note now includes a `createdAt` field (ISO 8601 string) set automatically when the note is created
- `GET /notes` and `POST /notes` responses include the `createdAt` field

## Frontend

- Display the timestamp next to each note (e.g. "2 minutes ago" or a formatted date)
