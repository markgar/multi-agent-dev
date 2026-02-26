# Stretto

A multi-tenant management platform for arts organizations. Stretto provides tools to organize members, assign them to projects, and coordinate concerts across program years.

## Quick Start

### Prerequisites

- .NET 10 SDK
- Node.js 18+
- Git

### Building

```bash
# Backend
dotnet build

# Frontend
cd web && npm install && npm run build
```

### Running Locally

```bash
# Backend API (runs on http://localhost:5000)
dotnet run --project Stretto.Api

# Frontend dev server (runs on http://localhost:5173)
cd web && npm run dev
```

### Testing

```bash
# Backend tests
dotnet test

# Frontend tests
cd web && npm test

# E2E tests
cd web && npx playwright test
```

See SPEC.md for architecture and REQUIREMENTS.md for feature details.
