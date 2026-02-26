# Stretto

Stretto is a multi-tenant management platform designed for arts organizations. It provides tools to organize members, assign them to projects, and coordinate concerts across program years. The platform is built to run as SaaS, with each organization's data isolated within a single shared deployment.

## Core Concepts

### Organizations

An organization is the top-level tenant in Stretto (e.g., "Minnesota Chorale"). All other entities — members, projects, program years, auditions, etc. — belong to an organization. Data is isolated per organization. A SaaS admin role for managing organizations can be added later; for now, organizations are created via seed data.

### Members

Members are the individuals who belong to the organization. They can be assigned to one or more projects based on their roles and availability.

- **Fields**: Name, email address. Additional fields can be added later.
- **Registration**: Members are created automatically when they sign up for an audition. This is their entry point into the system.
- **Admin Management**: Admins can also manually add, edit, and deactivate members outside of the audition process.

### Projects

Projects represent individual concerts or performances. Each project tracks its assigned members and associated details.

- **Fields**: Name, start date, end date, description.
- **Date Range**: A project spans a date range (start and end dates). All events within the project should fall within this range.
- **Events**: Each project contains a list of **events** (see Events below).

### Program Years

A program year is the organizational time period (e.g., a season) that groups related projects together. All concerts within a given season fall under a single program year.

- **Fields**: Name (e.g., "2026-2027").
- **Current Year**: One program year can be marked as the **current** year. This is the default context when users log in.
- **Archival**: Program years can be archived to keep the interface focused on active seasons while preserving historical data.

### Auditions

An audition is a scheduled evaluation event tied to a **program year**. Admins define audition dates with time windows and block lengths, and the system generates individual time slots. Members sign up for available slots. Signing up for an audition is how new members are created in the system.

- **Notes**: Admins can take notes during each audition directly in the app.
- **Status Tracking**: Each audition slot has a status that admins can update (e.g., Pending, Accepted, Rejected, Waitlisted).

### Venues

A venue is a managed location where events take place (e.g., "First Lutheran Church", "Orchestra Hall"). Admins create and maintain a list of venues for the organization. Each venue can store contact information for the venue's point of contact, so this knowledge is preserved across admin transitions.

- **Fields**: Name, address, contact name, contact email, contact phone.

### Events (Rehearsals & Performances)

An event is a scheduled occurrence tied to a specific project. Each event has a date, start time, duration, and venue (selected from the managed venue list). Events are typed as either **Rehearsal** or **Performance**. Members check in to record their attendance at events.

### Project Materials

Resources associated with a project that admins share with members via links and uploaded documents. See the Features section for full details.

## Authentication & Roles

### Authentication

Authentication uses a **passwordless, email-based flow** with trusted browser cookies.

#### Long-Term Vision

1. The member enters their **email address** on the login screen.
2. The system sends an email containing a **6-digit numeric code**.
3. The member enters the code to verify their identity.
4. Upon successful verification, a **persistent cookie** is set in the browser, marking it as **trusted**.
5. On subsequent visits from the same browser, the cookie is detected and the member is **automatically logged in** — no email or code entry required.
6. If the cookie is missing or expired (e.g., new browser, cleared cookies), the full email-code flow is triggered again.

#### Current Implementation (Phase 1)

- Email verification is **not yet implemented** — there is no external email-sending system in place.
- For now, the member enters their **email address only** and is logged in immediately (no code, no email sent).
- A persistent trusted-browser **cookie** is still set, so automatic login on return visits works from the start.
- The email verification step will be added later as a drop-in enhancement without changing the cookie/trusted-browser mechanism.

#### Technical Notes

- The cookie should be **HttpOnly**, **Secure**, and use **SameSite=Strict** for security best practices.
- The cookie should contain or reference a **server-side session or token** — do not store user identity directly in the cookie.
- The backend should expose an endpoint to **validate the cookie** on page load and return the current user context (organization, role, etc.).
- The login endpoint should verify that the email belongs to an existing member (or create one in the audition sign-up flow) before setting the cookie.

### Roles

- **Member** — A standard user who can view their assignments and project details.
- **Admin** — Has full access to manage members, projects, and program years.

## Features

### Project Management

- Admins can **create and manage program years** to organize projects into seasons.
- Admins can **create projects** within a program year.
- Admins can **assign and unassign members** to/from projects.

### Member Assignment

- When assigning members to a project, admins should be able to browse or search the full member list and toggle assignments.

### Program Year Utilization Grid

A key view for admins to see the big picture of a program year at a glance.

- **Layout**: A grid/matrix view for a selected program year.
  - **Rows** = Members (listed down the page)
  - **Columns** = Projects/concerts (listed across the top)
  - **Cells** = Filled/highlighted when a member is assigned to that project; empty when not.
- **Sorting**: Members are sorted by utilization — most-assigned members appear at the top, least-assigned at the bottom.
- **Utilization indicator**: Each member row should show a count or percentage of how many projects they are assigned to out of the total in that program year.
- This view gives admins a quick way to spot under-utilized members, balance workloads, and identify gaps.

### Audition Management

Admins can set up and manage audition scheduling for the organization. Auditions are part of the program year lifecycle — each new program year will have its own set of auditions.

- **Audition Dates** — Admins create one or more audition dates, each with a defined start time and end time.
- **Block Length** — Admins select a block length (e.g., 10 minutes, 15 minutes) for each audition date. The block length must divide evenly into the total audition time window — no partial blocks are allowed.
- **Generated Slots** — Once a date and block length are configured, the system automatically generates the individual time slots within that window.
- **Member Sign-Up** — After an admin has finished setting up the audition schedule, members can browse available slots and sign up for one. Signing up for an audition automatically creates the member's account if they are new to the system.
- **Scope** — Auditions are tied to a program year. After auditions, members can then be assigned to projects within that program year.

### Project Materials

Each project has a materials section where admins can share resources with assigned members.

- **Links** — Admins can add external links (e.g., to sheet music stores, reference recordings, venue info) with a title and URL. Members can view and follow these links.
- **Documents** — Admins can upload files (e.g., PDFs, scores, schedules) to a project. Members can browse and download these documents.
- **Member View** — When a member logs in, they can navigate to any project they are assigned to and see all materials (links and documents) associated with that project.

### Event Management & Attendance

Admins can schedule events (rehearsals and performances) for each project and track member attendance.

- **Event Setup** — Admins create events for a project with the following details:
  - Type (Rehearsal or Performance)
  - Date
  - Start time
  - Length/duration
  - Venue (selected from the managed venue list)
- **Attendance Statuses** — Each member's attendance for an event can be one of:
  - *No status* (default — event hasn't happened or member hasn't responded)
  - *Present* — Member has checked in
  - *Excused* — Member has indicated in advance that they cannot attend
  - *Absent* — Member did not check in and did not mark themselves excused
- **Attendance Check-In** — Each event has a unique URL so that a QR code can be generated and displayed at the venue. Members scan the code, log in, and tap a single "I'm here" button to mark themselves present. The check-in process should be as frictionless as possible.
- **Excused Absence** — Members can go to their dashboard and mark themselves as excused for any upcoming event before it occurs.
- **Attendance View** — Admins can see the attendance status of all assigned members for each event.
### Notifications

- **Assignment Announcements** — After a program year's project assignments are finalized, admins can send an announcement email to all members with their assignments (which projects they are on).
- **Audition Announcements** — Admins can send notifications when audition sign-ups are open.
- **Unsubscribe** — Members must be able to opt out of notifications (delete themselves from the mailing list or toggle notifications off).
- **Implementation** — Notifications should use a **provider abstraction** (interface) so the delivery mechanism can be swapped later (e.g., SendGrid, SMTP). For now, the implementation is stubbed out — no actual emails are sent.

### Member Calendar

- Members can view a personal calendar showing all their upcoming events (rehearsals and performances) across all assigned projects.
- **iCal/Google Calendar Export** — Members can subscribe to or download an iCal feed (.ics) of their events, allowing them to add their schedule to Google Calendar, Apple Calendar, Outlook, etc.
## Technical Requirements

### Platform

- **.NET 10** — Target the latest .NET 10 framework for all backend services.
- Enable **nullable reference types** across all projects.
- Enforce formatting with `dotnet format` — configuration checked into the repository.

### Architecture

- Follow **clean architecture** principles with clear separation of concerns:
  - **Domain** — Core entities, value objects, and business rules. No external dependencies.
  - **Application** — Use cases, interfaces, and DTOs. Depends only on Domain.
  - **Infrastructure** — Data access, external services, and framework implementations. Implements Application interfaces.
  - **API** — ASP.NET Core Web API exposing RESTful endpoints. Thin controllers delegating to the Application layer. Must expose an **OpenAPI/Swagger** specification (see API Contract).
- **Project naming convention** — Use a consistent naming pattern for solution projects (e.g., `Stretto.Domain`, `Stretto.Application`, `Stretto.Infrastructure`, `Stretto.Api`, `Stretto.Web`). Each project maps to exactly one architectural layer so the agent always knows where to find and place code.

### Database

- Use **Entity Framework Core** with an **in-memory database** for now. A persistent database (e.g., SQL Server or PostgreSQL) can be swapped in later via configuration.
- Use **explicit Fluent API configuration** for all entity mappings — no data annotations or convention-based configuration. This keeps the domain entities clean and makes the mappings unambiguous for the AI agent.
- Key entities: Organizations, Members, Projects, Program Years, Project Assignments, Venues, Events (Rehearsals/Performances), Attendance Records, Audition Dates, Audition Slots (with notes, status, and optional member sign-up), Project Materials (Links, Documents).
- All entities carry an `OrganizationId` foreign key for tenant isolation. Queries should be automatically scoped to the current user's organization.

### Frontend

- Use **React with TypeScript** for the web frontend.
  - Use **Vite** as the build tool for fast development.
  - Use **React Router** for client-side routing.
  - Enable **TypeScript strict mode** for maximum type safety.
  - Use **shadcn/ui** as the component library for all UI elements (buttons, cards, tables, dialogs, forms, dropdowns, etc.). Initialize with `npx shadcn@latest init` and add components as needed with `npx shadcn@latest add <component>`. shadcn/ui copies components into the project as source files — customize them when needed but prefer the defaults for consistency.
  - Use **Tailwind CSS** for all styling (required by shadcn/ui). Use utility classes directly — no separate CSS files or CSS-in-JS. Follow a mobile-first approach with Tailwind's responsive prefixes (`sm:`, `md:`, `lg:`).
  - Use **React Hook Form** with **Zod** for all forms. shadcn/ui's `<Form>` component is built on these — every form in the app should follow the same pattern: define a Zod schema, create a form with `useForm<z.infer<typeof schema>>`, and use shadcn `<FormField>` components. No ad-hoc `useState`-based form handling.
  - Use **Tanstack Query (React Query)** for all API data fetching and mutations. Every API call should go through `useQuery` or `useMutation` — no raw `useEffect` + `fetch` patterns. This provides consistent loading/error states, caching, and automatic refetching.
  - Use **Tanstack Table** for all data tables and grids (member lists, project lists, utilization grid, audition slots). shadcn/ui's `<DataTable>` component is built on Tanstack Table. Use it for sorting, filtering, and pagination.
  - Use **Zustand** for lightweight global state (auth context, current organization, current program year). Prefer Zustand stores over React Context for cross-cutting state.
  - Use **date-fns** for all date/time formatting, parsing, and manipulation. Do not use `moment.js` or raw `Date` methods.
  - Use **Lucide React** for all icons (bundled with shadcn/ui). Do not add other icon libraries.
  - Components should use semantic HTML elements and `data-testid` attributes to enable reliable element selection by AI agents and automated tests.
  - Prefer simple, page-based navigation with clearly labeled forms and controls.
  - The application must be **fully responsive** and work well on both **desktop browsers** and **mobile phones**. Ensure all views — including the utilization grid, calendars, forms, and navigation — are usable on small screens without horizontal scrolling or broken layouts.

### UI & Design

The application should look like a modern, professional SaaS tool — clean, spacious, and consistent. The following guidelines ensure the AI agent produces a cohesive UI without needing a designer.

#### Color & Theme

- Use a **neutral base** (white/light gray backgrounds, dark gray text) with a single **brand accent color** (indigo, e.g., Tailwind's `indigo-600`) for primary actions, active nav items, and links.
- Use semantic status colors consistently everywhere: green for success/active/present, yellow/amber for warnings/pending, red for errors/absent/rejected, gray for archived/inactive.
- Audition slot statuses should be color-coded: Pending = amber, Accepted = green, Rejected = red, Waitlisted = blue.
- Attendance status badges should use subtle background tints (e.g., `bg-green-100 text-green-800` for Present) rather than solid blocks of color.

#### Layout

- **Desktop (≥1024px)**: Fixed left sidebar (240px) with navigation, content area fills remaining width. Sidebar shows the organization name at the top, nav links in the middle, and the current user's name/role at the bottom.
- **Tablet (768–1023px)**: Collapsible sidebar — collapsed to icons by default, expands on hover or tap.
- **Mobile (<768px)**: No sidebar. Use a **bottom tab bar** for primary navigation (4–5 tabs max). Secondary pages are accessed via back navigation. The top bar shows the page title and the organization name.
- All pages should have a max content width (e.g., `max-w-7xl`) centered on wide screens so content doesn't stretch uncomfortably on ultrawide monitors.

#### Components & Patterns

- **Cards**: Use cards (white background, subtle border or shadow, rounded corners) as the primary container for content sections — project details, member profiles, event info, dashboard summary tiles.
- **Tables**: Use clean, striped tables for list views (members, projects, events, audition slots). Include column headers, hover highlighting, and pagination. On mobile, tables should collapse into a **card-per-row** layout rather than a horizontally scrolling table.
- **Forms**: Labels above inputs. Inputs should be full-width within their container. Group related fields visually. Use inline validation messages (red text below the field). Primary submit button is the accent color; secondary/cancel buttons are neutral.
- **Buttons**: Three tiers — primary (accent color, solid), secondary (outlined or light background), and destructive (red). Minimum tap target of 44×44px on mobile.
- **Modals/Dialogs**: Use for confirmations and quick-edit forms (e.g., assigning members, creating events). Keep modals focused — one task per modal, no scrolling if avoidable.
- **Empty States**: Every list view should have a friendly empty state (icon + message + call-to-action button, e.g., "No projects yet — create your first project").
- **Loading States**: Show skeleton loaders (pulsing placeholder shapes) for page content while API calls are in flight. Never show a blank page.
- **Error States**: API errors should show an inline error banner with a retry button — not a full-page error.
- **Toast Notifications**: Use brief toast messages (bottom-right on desktop, top on mobile) for action confirmations ("Member added", "Event created", "Attendance recorded").

#### Utilization Grid Specific

- The utilization grid is the highest-density view. On desktop, show the full member × project matrix with filled/empty cells. Each row shows the member name and a utilization count/percentage. Column headers show project names (truncated with tooltip on hover if long).
- On mobile, the utilization grid should switch to a **list view grouped by member** — each member is a collapsible section showing their assigned projects.
- Use the accent color for filled cells and a light gray for empty cells. High-utilization members should be visually distinct (e.g., bold row or subtle background highlight).

#### Member Check-In Specific

- The QR-code check-in page should be minimal and mobile-optimized — large "I'm here" button, event name, and venue. No navigation chrome.
- The check-in button should be full-width, tall (56px+), and use a strong green color with a checkmark icon on success.

#### Typography & Spacing

- Use Tailwind's default font stack (system fonts). No custom web fonts — they slow page load and add complexity.
- Use consistent heading sizes: page titles `text-2xl font-bold`, section headings `text-lg font-semibold`, card titles `text-base font-medium`.
- Use Tailwind's spacing scale consistently — `p-4` / `p-6` for card padding, `gap-4` / `gap-6` for grid gaps, `space-y-4` for stacked elements.

### API Contract

- The ASP.NET Core API should expose an **OpenAPI/Swagger** specification.
- Use an **auto-generated TypeScript API client** (e.g., via `openapi-typescript-codegen` or similar) so the frontend always matches the backend contract. This eliminates manual API wiring and reduces errors when the API changes.
- The generated client should be checked into the repository so changes are visible in diffs.

### File Storage

- Use a **storage provider abstraction** (interface) so the underlying storage can be swapped later (e.g., to Azure Blob Storage).
- For now, store uploaded documents on the **local file system**.
- Organize files in a structured directory layout (e.g., by organization, program year, and project).

### Seed Data

- The app should start with seed data for development/demo purposes:
  - Organization: "My Choir"
  - Admin user: `admin@stretto-demo.example` (belongs to "My Choir")
  - Member user: `member@stretto-demo.example` (belongs to "My Choir")

### Business Rules to Enforce

- Audition block length must divide evenly into the audition time window — the API should validate this and reject invalid configurations.
- Audition slots should be auto-generated server-side when an audition date is created or updated.
- Members should not be able to sign up for a slot that is already taken.
- Signing up for an audition creates a new member record if the email does not already exist.
- The utilization grid data (assignment counts, sorting) should be computed server-side and returned via a dedicated API endpoint for performance.
- Events must fall within their project's start and end date range — the API should validate this.

### Testing

- Structure the solution so that Domain and Application layers can be **unit tested** independently of Infrastructure.
- API endpoints should support **integration testing** with a test database.
- Frontend pages should be testable via **Playwright** using `data-testid` attributes.
- Frontend components should have **React Testing Library** unit tests.
- All tests must be runnable from the command line with a single command (e.g., `dotnet test` for backend, `npm test` for frontend, `npx playwright test` for end-to-end).

### AI Agent Maintainability

This codebase is maintained entirely by an AI coding agent. The following requirements ensure the agent can reliably understand, modify, test, and verify the system:

- **Consistent project structure** — Follow strict conventions for file/folder organization. Each feature area should have a predictable layout in both backend and frontend.
- **Small, focused files** — Keep files under ~200 lines. One component/class/module per file. This makes targeted edits reliable.
- **Strong typing everywhere** — TypeScript strict mode on the frontend; no `any` types. C# nullable reference types enabled on the backend. The agent relies on the type system to understand contracts.
- **Explicit over implicit** — Avoid magic strings, convention-based routing, or auto-discovery patterns. Prefer explicit registration, explicit imports, and explicit configuration.
- **Linting and formatting enforced** — Use ESLint + Prettier for the frontend and `dotnet format` for the backend. Configuration files checked in. The agent should be able to auto-fix formatting.
- **Self-documenting code** — Use clear, descriptive names for files, functions, and variables. Add brief comments only where intent is non-obvious.
- **Runnable with simple commands** — The project must build, run, and test with straightforward commands documented in a top-level README. No complex setup steps.
- **OpenAPI as the source of truth** — The API contract is defined by the backend's OpenAPI spec. The frontend client is auto-generated from it. This removes ambiguity about API shapes.
- **Comprehensive test coverage** — Every feature should have tests the agent can run to verify changes haven't broken anything. Tests are the agent's primary feedback mechanism.
- **No manual steps** — Everything the agent needs to do (build, test, lint, generate API client) should be scriptable and automatable.

## Navigation Structure

### Admin Navigation

- **Dashboard** — Overview of the current program year: upcoming events, recent activity.
- **Program Years** — List/create/archive program years; drill into a year to see its projects.
- **Projects** — List/create projects within a program year; drill into a project for events, materials, and member assignments.
- **Utilization Grid** — The matrix view for the current (or selected) program year.
- **Members** — Browse/search all members; view profiles and assignments; manually add, edit, or deactivate members.
- **Auditions** — Set up audition dates and slots for a program year; view sign-ups; take notes and set statuses.
- **Venues** — Manage the list of venues and their contact information.
- **Notifications** — Compose and send announcements (assignment emails, audition announcements).

### Member Navigation

- **My Projects** — List of projects the member is assigned to; drill in to see events and materials.
- **My Calendar** — Personal calendar of all upcoming rehearsals and performances, with iCal export.
- **Auditions** — Browse open audition slots and sign up (also serves as the registration entry point for new members).
- **Profile** — View/edit name, email; manage notification preferences.

### Shared

- The top nav shows the organization name and the user's role.
- Admin sees the full admin nav; member sees the simplified member nav.
- Each event has a unique URL to support QR-code-based check-in.
