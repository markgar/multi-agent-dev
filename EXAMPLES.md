# Examples

Ready-to-run commands for different project types and languages.

---

## 👋 Hello World

A minimal starter — one file, no dependencies.

**.NET/C#**
```bash
agentic-dev go --name "hello-world" \
  --description "a C# console app that prints Hello World"
```

**Python**
```bash
agentic-dev go --name "hello-world" \
  --description "a Python CLI app that prints Hello World"
```

**Node.js**
```bash
agentic-dev go --name "hello-world" \
  --description "a Node.js CLI app that prints Hello World"
```

---

## 🚀 Simple API

A REST API with CRUD endpoints, a database, and tests.

**.NET/C#**
```bash
agentic-dev go \
  --name "bookstore-api" \
  --description "a C# ASP.NET Core Web API for a bookstore with CRUD endpoints for books (title, author, ISBN, price, genre), an in-memory Entity Framework Core database (UseInMemoryDatabase), and xUnit tests"
```

**Python**
```bash
agentic-dev go \
  --name "bookstore-api" \
  --description "a Python FastAPI REST API for a bookstore with CRUD endpoints for books (title, author, ISBN, price, genre), SQLite with SQLAlchemy, and pytest tests"
```

**Node.js**
```bash
agentic-dev go \
  --name "bookstore-api" \
  --description "a Node.js Express REST API for a bookstore with CRUD endpoints for books (title, author, ISBN, price, genre), SQLite with Sequelize, and Jest tests"
```

---

## 🏗️ Full Stack

A multi-layer application with a web front-end, API, database, and integration tests. These take longer — the Builder scaffolds multiple projects, wires everything together, and builds the UI, all while the Reviewer and Tester provide feedback on each commit.

**.NET/C#**
```bash
agentic-dev go \
  --name "todo-app" \
  --description "a full-stack Todo application using the latest .NET SDK available on this machine. It should have three layers: (1) a Blazor web front-end for managing todos (add, complete, delete, list), (2) an ASP.NET Core Web API middle tier with RESTful endpoints for todos (id, title, isComplete), and (3) an in-memory Entity Framework Core database (UseInMemoryDatabase). Include a shared class library for the Todo model. The solution should use a single .sln file. Add xUnit integration tests that use WebApplicationFactory to test the API endpoints. Seed a few sample todos on startup."
```

**Python**
```bash
agentic-dev go \
  --name "todo-app" \
  --description "a full-stack Todo application with three layers: (1) a FastAPI REST API with RESTful endpoints for todos (id, title, is_complete), (2) a Jinja2-based web front-end served by FastAPI for managing todos (add, complete, delete, list), and (3) a SQLite database with SQLAlchemy ORM. Use Alembic for migrations. Include a Pydantic model for the Todo schema. Add pytest tests using httpx.AsyncClient and TestClient to test the API endpoints. Seed a few sample todos on startup."
```

**Node.js**
```bash
agentic-dev go \
  --name "todo-app" \
  --description "a full-stack Todo application with three layers: (1) an Express REST API with RESTful endpoints for todos (id, title, isComplete), (2) an EJS-based web front-end served by Express for managing todos (add, complete, delete, list), and (3) a SQLite database with Sequelize ORM. Include a Todo model. Add Jest tests using supertest to test the API endpoints. Seed a few sample todos on startup."
```
