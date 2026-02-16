# FieldCraft

FieldCraft is a multi-tenant field service management platform designed for trade service companies (HVAC, plumbing, electrical, general contracting). It provides tools to manage customers, schedule and dispatch jobs, track technician time, and generate invoices. The platform is built to run as SaaS, with each company's data isolated within a single shared deployment.

## Core Concepts

### Companies

A company is the top-level tenant in FieldCraft (e.g., "Northland Heating & Cooling"). All other entities — customers, jobs, technicians, invoices, etc. — belong to a company. Data is isolated per company. A SaaS admin role for managing companies can be added later; for now, companies are created via seed data.

### Customers

Customers are the people or businesses that request service. Each customer belongs to a company and can have multiple service locations.

- **Fields**: Name, email, phone number, notes.
- **Service Locations**: Each customer can have one or more addresses on file. When creating a job, the dispatcher picks from the customer's saved locations. Locations include address, gate code or access notes, and an optional label (e.g., "Main Office", "Warehouse").
- **History**: A customer's profile shows a complete history of all past and upcoming jobs at any of their locations.

### Technicians

Technicians are the field workers who perform jobs. They belong to a company and have skills that determine which job types they can be dispatched to.

- **Fields**: Name, email, phone number, hourly rate.
- **Skills**: Each technician has a set of skill tags (e.g., "HVAC Install", "Electrical Troubleshoot", "Plumbing Repair"). Skills are managed at the company level — admins define the available skill tags and assign them to technicians.
- **Availability**: Technicians have a weekly availability schedule (e.g., Mon–Fri 8am–5pm). The scheduler uses this when assigning jobs.
- **Status**: Active or Inactive. Inactive technicians do not appear in the dispatch board.

### Jobs

A job is a single service visit to a customer location. Jobs are the core workflow unit in FieldCraft — they move through a lifecycle from request to completion to invoicing.

- **Fields**: Title, description, job type, priority (Low, Normal, Urgent, Emergency), estimated duration.
- **Job Types**: Defined at the company level (e.g., "Furnace Repair", "AC Install", "Pipe Replacement", "Panel Upgrade"). Each job type maps to one or more required skill tags. When dispatching, the system warns if the assigned technician lacks a required skill.
- **Lifecycle Statuses**:
  - *Requested* — Customer has asked for service; not yet scheduled.
  - *Scheduled* — Assigned to a technician with a date and time window.
  - *En Route* — Technician has started traveling to the location.
  - *In Progress* — Technician is on-site and working.
  - *Completed* — Work is finished; ready for invoicing.
  - *Invoiced* — Invoice has been generated.
  - *Cancelled* — Job was cancelled before completion.
- **Status transitions** must follow the defined lifecycle order — a job cannot jump from Requested to Completed, for example. The API enforces valid transitions.

### Service Windows

When a job is scheduled, it is assigned a **service window** — a date and an approximate time range (e.g., "Feb 20, 8:00 AM – 12:00 PM"). This is the window communicated to the customer. The actual start time depends on the technician's route that day.

### Work Logs

When a technician is on-site, they log their work. A work log captures what was done, parts used, and time spent.

- **Fields**: Description of work performed, start time, end time (auto-calculated duration), parts used (free-text list for now).
- **Photos**: Technicians can attach photos to a work log (before/after shots, damage documentation, serial number plates). Photos are stored via a storage abstraction.
- **Customer Signature**: At the end of a job, the technician captures the customer's signature on the mobile device using a canvas-based signature pad (use the `react-signature-canvas` npm package). The signature image is stored with the work log.

### Invoices

After a job is completed, an invoice is generated from the work log data.

- **Line Items**: Labor (hours × technician rate), parts/materials (manually entered amounts), and any flat-fee charges.
- **Tax**: A configurable tax rate at the company level, applied to the subtotal.
- **Status**: Draft, Sent, Paid, Overdue, Void.
- **PDF Generation**: Invoices can be exported as a PDF with the company's branding (name, logo, address, phone).
- **Email**: Admins can email the invoice PDF directly to the customer from within the app (uses the notification provider abstraction).

### Equipment Records

Customers can have equipment tracked at each service location (e.g., "Trane XV20i Heat Pump — installed 2023, serial #XYZ"). This allows technicians to see equipment history and maintenance records before arriving on-site.

- **Fields**: Equipment type, manufacturer, model, serial number, install date, warranty expiration, notes.
- **Linked to Location**: Equipment belongs to a specific service location.
- **Service History**: Each job performed at a location can be linked to a piece of equipment, building a maintenance timeline.

### Price Book

A price book is a company-managed catalog of standardized charges used for estimates and invoices.

- **Labor Codes**: Standard labor items (e.g., "Diagnostic Fee", "Replace Capacitor") with unit price rules.
- **Parts/Materials**: Standard parts with base price and default markup.
- **Flat-Rate Items**: Fixed-price services (e.g., "Water Heater Flush").
- **Discount Rules**: Optional rules limiting how much dispatchers can discount without admin approval.

### Estimates

An estimate is a customer-facing quote that can be approved and converted into a scheduled job.

- **Statuses**: Draft, Sent, Approved, Rejected, Expired.
- **Options**: Estimates can include multiple options (Good/Better/Best) with different line items and totals.
- **Conversion**: An approved estimate can be converted into a job while preserving the selected option and pricing.

### Inventory (Warehouse & Truck Stock)

Inventory tracks parts and materials used on jobs.

- **Warehouse Stock**: Company-level stock counts.
- **Truck Stock**: Per-technician stock counts.
- **Reservations**: Parts can be reserved for a specific job.
- **Low Stock Alerts**: Admins can configure reorder thresholds.

## Authentication & Roles

### Authentication

Authentication uses a **passwordless, email-based flow** with trusted device cookies.

#### Long-Term Vision

1. The user enters their **email address** on the login screen.
2. The system sends an email containing a **6-digit numeric code**.
3. The user enters the code to verify their identity.
4. Upon successful verification, a **persistent cookie** is set in the browser, marking it as **trusted**.
5. On subsequent visits from the same device, the cookie is detected and the user is **automatically logged in**.
6. If the cookie is missing or expired (e.g., new device, cleared cookies), the full email-code flow is triggered again.

#### Current Implementation (Phase 1)

- Email verification is **not yet implemented** — there is no external email-sending system in place.
- For now, the user enters their **email address only** and is logged in immediately (no code, no email sent).
- A persistent trusted-device **cookie** is still set, so automatic login on return visits works from the start.
- The email verification step will be added later as a drop-in enhancement without changing the cookie/trusted-device mechanism.

#### Technical Notes

- The cookie should be **HttpOnly**, **Secure**, and use **SameSite=Strict** for security best practices.
- The cookie should contain or reference a **server-side session or token** — do not store user identity directly in the cookie.
- The backend should expose an endpoint to **validate the cookie** on page load and return the current user context (company, role, etc.).
- The login endpoint should verify that the email belongs to an existing user before setting the cookie.

### Roles

- **Technician** — A field worker who can view their assigned jobs, log work, capture signatures, and update job status from the field.
- **Dispatcher** — Can manage customers, create and schedule jobs, assign technicians, and view the dispatch board. Cannot manage company settings or invoices.
- **Admin** — Full access including company settings, technician management, invoicing, and reporting.

## Features

### Dispatch Board

The central scheduling view for dispatchers and admins. Shows the day's (or week's) job assignments at a glance.

- **Layout**: A table/grid view.
  - **Rows** = Technicians (listed down the page)
  - **Columns** = Time blocks across the day (or days across the week)
  - **Cells** = Job cards placed at their scheduled service window, color-coded by status.
- **Scheduling**: Each job card has an "Assign" button. Dispatchers select a technician from a dropdown and pick a service window using date/time inputs. No drag-and-drop — use explicit form controls for reliable, testable scheduling.
- **Unassigned Queue**: A sidebar panel shows all jobs in *Requested* status that have not yet been scheduled. Each job has an "Assign" button to open the scheduling form.
- **Skill Matching**: When a job is assigned to a technician, the system checks whether the technician has the required skills for the job type. If not, a warning is shown (but the assignment is still allowed — sometimes you need to send who's available).
- **Filtering**: Filter the board by job type, priority, or technician.

### Customer Management

- Admins and dispatchers can **create, edit, and search customers**.
- Each customer has a detail page showing their service locations, equipment records, and job history.
- **Quick Job Creation**: From a customer's profile, dispatchers can create a new job pre-filled with the customer's information.

### Job Workflow

The end-to-end lifecycle of a service job:

1. **Request** — A dispatcher creates a job (manually or from a customer request) with customer, location, job type, priority, and description.
2. **Schedule** — The dispatcher assigns a technician and a service window via the dispatch board.
3. **Notify** — When a job is scheduled, the customer receives a notification with the service window and technician name (uses notification provider abstraction; stubbed for now).
4. **Dispatch** — On the day of service, the technician sees the job on their mobile view. They tap "En Route" to update status.
5. **Arrive & Work** — The technician taps "Start Job" when on-site. They log work, attach photos, and note parts used.
6. **Complete** — The technician captures the customer's signature and taps "Complete Job". The job moves to *Completed*.
7. **Invoice** — An admin generates an invoice from the completed job's work log data.

### Technician Mobile View

Technicians primarily use FieldCraft on their phones while in the field. The mobile experience must be optimized for speed and simplicity.

- **My Jobs Today** — A list of today's assigned jobs in chronological order, showing customer name, address, service window, and job type.
- **Job Detail** — Tap a job to see full details: customer info, location (with a link to open in maps), equipment at that location, job description, and any prior work logs for the same equipment.
- **Status Updates** — Large, obvious buttons to transition job status: "En Route" → "Start Job" → "Complete Job".
- **Work Log Entry** — Simple form: what was done, start/end time (auto-populated), parts used, photo attachments, customer signature pad.

### Invoicing

- Admins can generate invoices from completed jobs.
- **Auto-Population**: Labor lines are calculated from work log time entries × technician hourly rate. Parts are listed from work log entries.
- **Editable**: Admins can adjust line items, add flat fees, or apply discounts before finalizing.
- **PDF Export**: Generate a branded PDF invoice.
- **Email**: Send the invoice to the customer directly from the app.
- **Payment Tracking**: Mark invoices as Paid or Overdue. No integrated payment processing for now — just status tracking.
- **Invoice List**: Filterable list of all invoices with status, date, customer, and amount. Supports searching by customer name or invoice number.

### Estimates (Quotes)

- Admins and dispatchers can create estimates for a customer and location.
- **Good/Better/Best**: Estimates can include multiple options with different scopes/prices.
- **Send to Customer**: Estimates can be sent to the customer (notification provider abstraction; stubbed for now).
- **Approval**: Customers can approve or reject an estimate from the estimate review status page (accessed via a secure link — see Customer Status Pages).
- **Convert**: Approved estimates can be converted into a job with the chosen option.

### Price Book

- Admins can manage a price book of standard labor codes, parts/materials, and flat-rate items.
- Estimate and invoice line items can be selected from the price book to reduce manual entry and improve consistency.
- The system supports company-specific pricing and an invoice number prefix.

### Inventory & Truck Stock

- Admins can manage warehouse inventory and assign truck stock to technicians.
- Technicians can record parts used on a job, decrementing truck stock.
- Dispatchers/admins can reserve parts for a job and see whether required parts are available.
- Low stock thresholds generate a reorder list for admins.

### Customer Status Pages

Customers can view job and estimate status via unique links — no login required. Each link contains a secure, unguessable token.

- **Job Status Page**: Shows the job's current status, scheduled service window, assigned technician name, and a timeline of status updates. The link is included in job-scheduled notifications.
- **Estimate Review Page**: Shows estimate options (Good/Better/Best) with line items and totals. The customer can approve or reject directly from this page. The link is included in estimate-sent notifications.
- **Invoice Page**: Shows invoice details and allows PDF download. The link is included in invoice-sent notifications.
- **No authentication required** — these are read-only (or single-action) pages accessed via secure tokens. No separate customer accounts or login flow.

### Reporting Dashboard

A summary view for admins showing key business metrics.

- **Revenue**: Total invoiced amount and total paid amount for the current month, with a comparison to the prior month.
- **Jobs**: Count of jobs by status (Requested, Scheduled, In Progress, Completed) for the current week.
- **Technician Utilization**: For each active technician, the percentage of their available hours that are booked with scheduled or in-progress jobs this week.
- **Average Job Duration**: Mean elapsed time from job start to completion, broken down by job type.
- **Outstanding Balance**: Total amount of unpaid invoices (Sent + Overdue).
- All metrics are computed server-side and returned via dedicated API endpoints.

### Notifications

- **Job Scheduled** — Customer receives a notification when their job is scheduled, including the service window and technician name.
- **Technician En Route** — Customer receives a notification when the technician marks "En Route".
- **Invoice Sent** — Customer receives the invoice via email.
- **Job Reminder** — The day before a scheduled job, the customer receives a reminder notification.
- **Unsubscribe** — Customers must be able to opt out of notifications.
- **Implementation** — Notifications should use a **provider abstraction** (interface) so the delivery mechanism can be swapped later (e.g., SendGrid, Twilio SMS, SMTP). For now, the implementation is stubbed out — no actual emails or texts are sent.

### Equipment Tracking

- Admins and dispatchers can add equipment records to a customer's service location.
- When a technician views a job, they see all equipment at that location with manufacturer, model, serial number, install date, and warranty status.
- When completing a work log, the technician selects which piece(s) of equipment the work was performed on.
- Equipment detail pages show a full service history timeline — every job linked to that equipment, with dates, descriptions, and technician names.

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
- **Project naming convention** — Use a consistent naming pattern for solution projects (e.g., `FieldCraft.Domain`, `FieldCraft.Application`, `FieldCraft.Infrastructure`, `FieldCraft.Api`, `FieldCraft.Web`). Each project maps to exactly one architectural layer so the agent always knows where to find and place code.

### Database

- Use **Entity Framework Core** with an **in-memory database** for now. A persistent database (e.g., SQL Server or PostgreSQL) can be swapped in later via configuration.
- Use **explicit Fluent API configuration** for all entity mappings — no data annotations or convention-based configuration. This keeps the domain entities clean and makes the mappings unambiguous for the AI agent.
- Key entities: Companies, Customers, Service Locations, Technicians, Skill Tags, Jobs, Job Types, Service Windows, Work Logs, Photos, Signatures, Invoices, Invoice Line Items, Equipment Records, Price Book Items (Labor/Part/Flat-Rate), Estimates (with options), Inventory Items, Warehouse Stock, Truck Stock, Inventory Reservations, Notification Preferences.
- All entities carry a `CompanyId` foreign key for tenant isolation. Queries should be automatically scoped to the current user's company.

### Frontend

- Use **React with TypeScript** for the web frontend.
  - Use **Vite** as the build tool for fast development.
  - Use **React Router** for client-side routing.
  - Enable **TypeScript strict mode** for maximum type safety.
  - Use **Tailwind CSS** for styling. No custom CSS files unless absolutely necessary — use Tailwind utility classes directly on elements.
  - Use **Headless UI** (`@headlessui/react`) for accessible interactive components (dropdowns, modals, comboboxes, dialogs). These provide behavior and accessibility without opinionated styling, so they pair well with Tailwind.
  - Components should use semantic HTML elements and `data-testid` attributes to enable reliable element selection by AI agents and automated tests.
  - Prefer simple, page-based navigation with clearly labeled forms and controls.
  - The application must be **fully responsive** and work well on both **desktop browsers** and **mobile phones**. Use a mobile-first approach to CSS. The technician mobile view must be optimized for one-hand use — large tap targets, minimal scrolling, clear status buttons.

### UI & Design

The application should look like a modern, professional SaaS tool — clean, spacious, and consistent. The following guidelines ensure the AI agent produces a cohesive UI without needing a designer.

#### Color & Theme

- Use a **neutral base** (white/light gray backgrounds, dark gray text) with a single **brand accent color** (blue, e.g., Tailwind's `blue-600`) for primary actions, active nav items, and links.
- Use semantic status colors consistently everywhere: green for success/completed/active, yellow/amber for warnings/pending, red for errors/urgent/overdue, gray for cancelled/inactive.
- Job priority should be color-coded: Low = gray, Normal = blue, Urgent = amber, Emergency = red.
- Job status badges should use subtle background tints (e.g., `bg-green-100 text-green-800`) rather than solid blocks of color.

#### Layout

- **Desktop (≥1024px)**: Fixed left sidebar (240px) with navigation, content area fills remaining width. Sidebar shows the company name/logo at the top, nav links in the middle, and the current user's name/role at the bottom.
- **Tablet (768–1023px)**: Collapsible sidebar — collapsed to icons by default, expands on hover or tap.
- **Mobile (<768px)**: No sidebar. Use a **bottom tab bar** for primary navigation (4–5 tabs max). Secondary pages are accessed via back navigation. The top bar shows the page title and a company logo.
- All pages should have a max content width (e.g., `max-w-7xl`) centered on wide screens so content doesn't stretch uncomfortably on ultrawide monitors.

#### Components & Patterns

- **Cards**: Use cards (white background, subtle border or shadow, rounded corners) as the primary container for content sections — job details, customer profiles, equipment records, dashboard metric tiles.
- **Tables**: Use clean, striped tables for list views (jobs, invoices, customers, inventory). Include column headers, hover highlighting, and pagination. On mobile, tables should collapse into a **card-per-row** layout rather than a horizontally scrolling table.
- **Forms**: Labels above inputs. Inputs should be full-width within their container. Group related fields visually. Use inline validation messages (red text below the field). Primary submit button is the accent color; secondary/cancel buttons are neutral.
- **Buttons**: Three tiers — primary (accent color, solid), secondary (outlined or light background), and destructive (red). Minimum tap target of 44×44px on mobile.
- **Modals/Dialogs**: Use for confirmations and quick-edit forms (e.g., assigning a technician, approving an estimate). Keep modals focused — one task per modal, no scrolling if avoidable.
- **Empty States**: Every list view should have a friendly empty state (icon + message + call-to-action button, e.g., "No jobs yet — create your first job").
- **Loading States**: Show skeleton loaders (pulsing placeholder shapes) for page content while API calls are in flight. Never show a blank page.
- **Error States**: API errors should show an inline error banner with a retry button — not a full-page error.
- **Toast Notifications**: Use brief toast messages (bottom-right on desktop, top on mobile) for action confirmations ("Job scheduled", "Invoice sent", "Estimate approved").

#### Dispatch Board Specific

- The dispatch board is the highest-density view. On desktop, show the full technician × time grid with job cards. Each job card shows: customer name (bold), job type, service window, and a colored status dot.
- On mobile, the dispatch board should switch to a **list view grouped by technician** — each technician is a collapsible section showing their jobs for the day in chronological order.
- The unassigned job queue should be a collapsible sidebar on desktop and a separate tab/view on mobile.

#### Technician Mobile View Specific

- The technician view should feel like a native app — full-bleed cards, large text, prominent status-transition buttons.
- The "En Route" / "Start Job" / "Complete Job" buttons should be full-width, tall (56px+), and use strong colors (blue → green → green with checkmark).
- The signature pad should be full-screen when activated, with clear "Save" and "Clear" buttons.
- Photo uploads should use a camera-first UI on mobile (trigger the device camera, not a file picker).

#### Typography & Spacing

- Use Tailwind's default font stack (system fonts). No custom web fonts — they slow page load and add complexity.
- Use consistent heading sizes: page titles `text-2xl font-bold`, section headings `text-lg font-semibold`, card titles `text-base font-medium`.
- Use Tailwind's spacing scale consistently — `p-4` / `p-6` for card padding, `gap-4` / `gap-6` for grid gaps, `space-y-4` for stacked elements.

### API Contract

- The ASP.NET Core API should expose an **OpenAPI/Swagger** specification.
- Use an **auto-generated TypeScript API client** (e.g., via `openapi-typescript-codegen` or similar) so the frontend always matches the backend contract. This eliminates manual API wiring and reduces errors when the API changes.
- The generated client should be checked into the repository so changes are visible in diffs.

### File Storage

- Use a **storage provider abstraction** (interface) so the underlying storage can be swapped later (e.g., to Azure Blob Storage or S3).
- For now, store uploaded photos, signatures, and invoice PDFs on the **local file system**.
- Organize files in a structured directory layout (e.g., by company, customer, and job).

### PDF Generation

- Use a **PDF generation abstraction** (interface) so the rendering library can be swapped later.
- For now, use a lightweight library (e.g., QuestPDF or similar) to generate invoice PDFs server-side.
- The PDF should include: company branding (name, address, phone), invoice number, date, customer info, line items, subtotal, tax, and total.

### Seed Data

- The app should start with seed data for development/demo purposes:
  - Company: "Northland Heating & Cooling"
  - Admin user: `admin@northlandhvac.com` (belongs to "Northland Heating & Cooling")
  - Dispatcher user: `dispatch@northlandhvac.com` (belongs to "Northland Heating & Cooling")
  - Technician users: `mike@northlandhvac.com`, `sarah@northlandhvac.com` (with different skill sets)
  - A handful of customers with service locations and equipment records
  - Predefined job types and skill tags for HVAC service

### Business Rules to Enforce

- Job status transitions must follow the defined lifecycle — the API should reject invalid transitions (e.g., Requested → Completed).
- A technician cannot be double-booked — if a new job's service window overlaps with an existing scheduled job for the same technician, the API should warn (but allow override by dispatchers).
- Service windows must not extend beyond the technician's availability hours for that day.
- When generating an invoice, labor hours must match the work log time entries — the API should validate consistency.
- Equipment warranty status should be auto-calculated from the warranty expiration date (Active, Expired, or No Warranty).
- Invoice numbers should be auto-generated with a company-specific sequential prefix (e.g., NHC-0001, NHC-0002).

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

- **Dashboard** — Reporting metrics overview: revenue, job counts, technician utilization, outstanding balance.
- **Dispatch Board** — Grid view of today's/this week's jobs by technician with form-based scheduling.
- **Jobs** — Searchable list of all jobs with filters for status, priority, job type, date range, and technician.
- **Customers** — Browse/search customers; drill into profiles for locations, equipment, and job history.
- **Technicians** — Manage technicians: add, edit, deactivate, assign skills, set availability.
- **Invoices** — List/create/manage invoices with status filters and search.
- **Estimates** — Create/send estimates; track approvals; convert to jobs.
- **Price Book** — Manage standardized labor, parts, and flat-rate items.
- **Inventory** — Warehouse stock, truck stock, reservations, low-stock alerts.
- **Equipment** — Browse all tracked equipment across customers; search by serial number, type, or warranty status.
- **Settings** — Company profile (name, logo, address, phone), job types, skill tags, tax rate, invoice number prefix.

### Dispatcher Navigation

- Same as Admin except without Settings and Invoices sections. Dispatchers can create estimates but cannot finalize invoices.

### Technician Navigation (Mobile-Optimized)

- **My Jobs Today** — Today's assigned jobs in chronological order with quick-status buttons.
- **Job Detail** — Full job info, customer details, location with maps link, equipment at location, work log form.
- **My Schedule** — Week view of assigned jobs.
- **Profile** — View skills, availability, and contact info.

### Shared

- The top bar shows the company name and the user's role.
- Admin sees full admin nav; dispatcher sees the dispatch-focused nav; technician sees the simplified mobile nav.
- **Desktop**: Fixed left sidebar with icon + label nav links. Active page is highlighted with the accent color.
- **Mobile**: Bottom tab bar with 4–5 primary destinations (icons + short labels). Secondary pages use a top bar with a back arrow and page title.
- **Transitions**: Use simple fade transitions between pages (no complex animations). Page loads should feel instant — use optimistic UI updates where appropriate.
