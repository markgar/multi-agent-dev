# Stretto Technical Specification

## Overview

Stretto is a SaaS platform for managing arts organizations. It enables member registration via auditions, project/concert management, event scheduling, attendance tracking, and material sharing. All data is isolated per organization (multi-tenant).

## Tech Stack

- **Backend**: .NET 10, ASP.NET Core Web API, Entity Framework Core (in-memory database; SQL Server/PostgreSQL configurable)
- **Frontend**: React 18 + TypeScript, Vite, shadcn/ui (Tailwind CSS), React Hook Form + Zod, Tanstack Query, Zustand
- **API Contract**: OpenAPI/Swagger with auto-generated TypeScript client
- **Storage**: Pluggable abstraction (local filesystem for now)
- **Authentication**: Passwordless email-based flow with trusted browser cookies (email verification stubbed for phase 1)

## Architecture

**Clean Architecture** with strict separation of concerns:
- **Domain** — Core entities, business rules, no external dependencies (organizations, members, projects, program years, auditions, events, venues, attendance)
- **Application** — Use cases, interfaces (repositories, services, notifications, storage), DTOs. Depends only on Domain.
- **Infrastructure** — EF Core DbContext, Fluent API mappings, notification stubs, file storage implementation. Implements Application interfaces.
- **Api** — ASP.NET Core controllers, thin wrappers delegating to Application. Exposes OpenAPI.
- **Web** — React SPA. Generated API client from OpenAPI spec.

Project structure: `Stretto.Domain`, `Stretto.Application`, `Stretto.Infrastructure`, `Stretto.Api`, `Stretto.Web`.

## Cross-Cutting Concerns

**Multi-tenancy**: Every entity carries `OrganizationId`. All queries automatically scoped to current user's organization.

**Authentication**: Email-based (immediate login phase 1; email verification deferred). Server-side session/token. HttpOnly + Secure + SameSite=Strict cookies. Validation endpoint on page load.

**Error Handling**: Exceptions wrapped at API layer; consistent error response schema with user-friendly messages.

**Validation**: Domain-level business rules enforced (e.g., audition block length divides evenly, events within project date range). API layer validates DTOs via FluentValidation.

**Notifications**: Provider abstraction (interface). Phase 1 stubbed; can plug in SendGrid/SMTP later.

**File Storage**: Provider abstraction (interface). Phase 1 uses local filesystem; can swap to Azure Blob later.

## Acceptance Criteria

- ✓ Organizations are isolated tenants
- ✓ Members can register via audition sign-up (creates account)
- ✓ Admins can manage projects, program years, members, venues, auditions
- ✓ Members can be assigned to projects; utilization grid shows assignments
- ✓ Events (rehearsals/performances) can be scheduled per project with venues
- ✓ Attendance tracked via QR-code check-in and excuse marking
- ✓ Project materials (links/documents) shared with assigned members
- ✓ Members see personal calendar of upcoming events; iCal export available
- ✓ Audition slots auto-generated; members sign up; admins set statuses/notes
- ✓ Notifications sent for assignments and auditions (stubbed provider)
- ✓ Frontend fully responsive (desktop nav, tablet/mobile optimized)
- ✓ API fully tested; frontend pages tested via Playwright
