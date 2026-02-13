# Notes App — Add Delete

Add delete functionality to the existing notes application.

## Backend

- Add `DELETE /notes/{id}` — removes the note with the given id, returns 204 on success, 404 if not found

## Frontend

- Add a "Delete" button next to each note in the list
- Clicking delete calls `DELETE /notes/:id` and refreshes the list
