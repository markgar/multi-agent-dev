# LedgerLine

LedgerLine is a multi-tenant ERP platform designed for small and medium businesses. It provides integrated tools to manage contacts, products, sales, purchasing, inventory, and basic accounting — all in one system. The platform is built to run as SaaS, with each business's data isolated within a single shared deployment.

## Core Concepts

### Businesses

A business is the top-level tenant in LedgerLine (e.g., "Summit Supply Co."). All other entities — contacts, products, orders, invoices, accounts, etc. — belong to a business. Data is isolated per business. A SaaS admin role for managing businesses can be added later; for now, businesses are created via seed data.

- **Fields**: Name, legal name, tax ID, address, phone, email, website, logo, fiscal year start month, default currency (USD).
- **Settings**: Tax rate, invoice number prefix, PO number prefix, payment terms default (Net 30, Net 60, etc.).

### Contacts

A contact is a person or company that the business transacts with. Contacts are unified — the same contact can be both a customer and a vendor, avoiding duplicate records.

- **Fields**: Name, company name, email, phone, billing address, shipping address, notes.
- **Type Tags**: A contact can be tagged as Customer, Vendor, or both. Filtering by type is available throughout the app.
- **Credit Limit**: Optional credit limit for customer-tagged contacts. The system warns when a new sales order would exceed the limit.
- **Payment Terms**: Per-contact payment terms override the business default (e.g., this customer gets Net 45 instead of the default Net 30).
- **History**: A contact's profile shows a complete transaction history — all quotes, sales orders, invoices, purchase orders, and bills associated with them.

### Products

A product is anything the business buys or sells. Products can be physical inventory items or non-inventory services.

- **Fields**: Name, SKU, description, category, unit of measure (e.g., each, box, hour, kg).
- **Product Type**: Inventory Item (tracked in stock), Non-Inventory Item (purchased/sold but not tracked in stock), or Service (labor/time-based).
- **Pricing**:
  - **Sale Price**: Default price charged to customers.
  - **Cost Price**: Default price paid to vendors.
  - These are defaults — prices can be overridden on individual order lines.
- **Tax Behavior**: Taxable or Tax-Exempt. Applied automatically to order line items.
- **Reorder Point**: For Inventory Items, the stock level at which a low-stock alert is generated.
- **Preferred Vendor**: Optional link to a vendor contact for quick purchase order creation.

### Chart of Accounts

The chart of accounts is the foundation of the accounting system. Each account categorizes one type of financial activity.

- **Account Types**: Asset, Liability, Equity, Revenue, Expense.
- **Sub-Types**: More specific classifications within each type (e.g., Asset → Cash, Accounts Receivable, Inventory; Liability → Accounts Payable, Credit Card; Revenue → Sales, Service Revenue; Expense → Cost of Goods Sold, Rent, Utilities).
- **Fields**: Account number, name, type, sub-type, description, is-active flag.
- **System Accounts**: Certain accounts are created automatically and cannot be deleted — Accounts Receivable, Accounts Payable, Inventory Asset, Sales Revenue, Cost of Goods Sold, Retained Earnings. These are used by automated journal entries.
- **Numbering Convention**: Assets start at 1000, Liabilities at 2000, Equity at 3000, Revenue at 4000, Expenses at 5000. Users can create accounts at any number within the range.

### Journal Entries

A journal entry is the fundamental accounting record. Every financial transaction ultimately results in one or more journal entries that debit and credit accounts.

- **Fields**: Date, reference number (auto-generated), memo/description, line items.
- **Line Items**: Each line has an account, debit amount or credit amount (never both), and an optional memo.
- **Balance Rule**: Total debits must equal total credits. The API rejects unbalanced entries.
- **Automatic Entries**: Most journal entries are created automatically when invoices, bills, and payments are recorded. Manual journal entries are available for adjustments, accruals, and corrections.
- **Status**: Draft (editable) or Posted (locked — can only be reversed with a new entry).

### Quotes

A quote (also called an estimate) is a proposal sent to a customer before a sale is confirmed.

- **Fields**: Quote number (auto-generated), date, expiration date, customer contact, line items, notes, terms and conditions.
- **Line Items**: Each line references a product, with quantity, unit price, discount percentage, tax applicability, and line total.
- **Statuses**: Draft, Sent, Accepted, Rejected, Expired.
- **Conversion**: An accepted quote can be converted into a sales order with one click, carrying over all line items and pricing.
- **PDF Export**: Quotes can be exported as branded PDF documents.

### Sales Orders

A sales order is a confirmed commitment to deliver products or services to a customer.

- **Fields**: SO number (auto-generated), date, customer contact, shipping address, line items, payment terms, notes.
- **Line Items**: Same structure as quotes — product, quantity, unit price, discount, tax, line total.
- **Statuses**: Draft, Confirmed, Partially Fulfilled, Fulfilled, Cancelled.
- **Fulfillment**: When items are shipped/delivered, the sales order is partially or fully fulfilled. Fulfillment decrements inventory for Inventory Items.
- **Invoicing**: A confirmed sales order can be converted into an invoice. Partial invoicing is supported — invoice selected lines or quantities.

### Invoices

An invoice is a request for payment sent to a customer. Invoices drive the Accounts Receivable ledger.

- **Fields**: Invoice number (auto-generated with business prefix, e.g., SS-0001), date, due date (calculated from payment terms), customer contact, line items, subtotal, tax, total, amount paid, balance due.
- **Line Items**: Product, quantity, unit price, discount, tax, line total.
- **Statuses**: Draft, Sent, Partially Paid, Paid, Overdue, Void.
- **Accounting Impact**: When an invoice is posted (status moves from Draft to Sent), the system automatically creates a journal entry: debit Accounts Receivable, credit Sales Revenue (and credit Tax Payable if applicable).
- **Overdue Detection**: Invoices past their due date are automatically flagged as Overdue.
- **PDF Export**: Invoices can be exported as branded PDF documents.
- **Email**: Invoices can be emailed directly to the customer (uses notification provider abstraction; stubbed for now).

### Payments Received

A payment received records money coming in from a customer against one or more outstanding invoices.

- **Fields**: Payment date, customer contact, payment method (Cash, Check, Bank Transfer, Credit Card, Other), reference number (e.g., check number), amount, memo.
- **Application**: A single payment can be applied across multiple invoices. The system tracks how much of each invoice is paid.
- **Accounting Impact**: Debit Cash/Bank account, credit Accounts Receivable. Updates invoice statuses automatically (Partially Paid or Paid).
- **Overpayment**: If a payment exceeds outstanding balances, the excess is recorded as a customer credit.

### Recurring Invoices

A recurring invoice is a template that automatically generates invoices on a schedule — useful for retainers, subscriptions, and recurring service fees.

- **Fields**: Customer contact, line items, frequency (Weekly, Monthly, Quarterly, Yearly), start date, end date (optional — runs indefinitely if omitted), next invoice date.
- **Statuses**: Active, Paused, Completed (end date reached).
- **Generation**: When the next invoice date arrives, the system creates a new invoice from the template with the current date and due date (calculated from payment terms). The next invoice date advances by the frequency interval.
- **Accounting Impact**: Each generated invoice follows the same journal entry rules as a regular invoice — debit AR, credit Revenue.
- **Management**: Users can pause, resume, edit, or cancel a recurring invoice at any time. Edits apply to future invoices only — already-generated invoices are not affected.

### Credit Notes

A credit note (also called a credit memo) is issued to a customer to reduce the amount they owe — for returns, overcharges, or adjustments.

- **Fields**: Credit note number (auto-generated with prefix, e.g., CN-0001), date, customer contact, line items, subtotal, tax, total.
- **Line Items**: Product or account, quantity, unit price, tax, line total. Typically references the original invoice line being credited.
- **Linked Invoice**: A credit note can optionally be linked to a specific invoice for audit clarity.
- **Statuses**: Draft, Issued.
- **Application**: An issued credit note can be applied to one or more outstanding invoices to reduce their balance. Any unapplied amount remains as a customer credit balance.
- **Accounting Impact**: Debit Sales Revenue (and Tax Payable if applicable), credit Accounts Receivable. The reverse of an invoice.
- **Refunds**: If the customer has no outstanding invoices, a credit note can be converted into a refund — debit AR, credit Cash.

### Expenses

An expense is a one-off business expenditure not tied to a vendor bill — petty cash purchases, credit card charges, employee reimbursements, etc.

- **Fields**: Date, expense account (from chart of accounts), amount, payment method, vendor contact (optional), category, description, receipt attachment.
- **Categories**: User-defined categories for grouping (e.g., Travel, Meals, Office Supplies, Fuel). Managed at the business level.
- **Receipt Attachments**: Users can upload a photo or PDF of the receipt. Stored via the file storage abstraction.
- **Accounting Impact**: Debit the selected expense account, credit Cash/Bank account. A journal entry is created automatically when the expense is saved.
- **Recurring Expenses**: An expense can optionally be marked as recurring with a frequency (same options as recurring invoices). The system auto-creates the expense entry on schedule.

### Purchase Orders

A purchase order (PO) is a request to buy products or services from a vendor.

- **Fields**: PO number (auto-generated with prefix), date, vendor contact, shipping address (defaults to business address), line items, expected delivery date, notes.
- **Line Items**: Product, quantity, unit cost, line total.
- **Statuses**: Draft, Sent, Partially Received, Received, Cancelled.
- **Receiving**: When items arrive, the user records a receipt against the PO. Receiving increments inventory for Inventory Items. Partial receiving is supported.
- **Quick PO**: From a product's low-stock alert, a user can create a PO pre-filled with the product and its preferred vendor.

### Bills

A bill is a vendor's invoice to the business — it represents money owed. Bills drive the Accounts Payable ledger.

- **Fields**: Bill number (vendor's invoice number), date, due date, vendor contact, line items, subtotal, tax, total, amount paid, balance due.
- **Line Items**: Product or expense account, quantity, unit cost, line total.
- **Statuses**: Draft, Received, Partially Paid, Paid, Overdue.
- **Linked to PO**: A bill can optionally be linked to a purchase order for three-way matching (PO → Receipt → Bill).
- **Accounting Impact**: When a bill is posted, the system creates a journal entry: debit Expense or Inventory account, credit Accounts Payable.

### Payments Made

A payment made records money going out to a vendor against one or more outstanding bills.

- **Fields**: Payment date, vendor contact, payment method, reference number, amount, memo.
- **Application**: A single payment can be applied across multiple bills.
- **Accounting Impact**: Debit Accounts Payable, credit Cash/Bank account.

### Inventory

Inventory tracks the quantity on hand for all Inventory Item type products.

- **Warehouses**: A business can have one or more warehouse locations. Each warehouse tracks stock independently.
- **Stock Levels**: Quantity on hand, quantity reserved (allocated to confirmed sales orders not yet fulfilled), quantity available (on hand minus reserved).
- **Stock Movements**: Every inventory change is recorded as a stock movement with a type (Purchase Receipt, Sales Fulfillment, Adjustment, Transfer) and a reference to the source document.
- **Adjustments**: Manual stock adjustments for damaged goods, shrinkage, or physical count corrections. Each adjustment requires a reason.
- **Transfers**: Move stock between warehouses.
- **Valuation**: Use weighted-average cost method for inventory valuation. The system tracks the average cost per unit as stock is received at different prices.
- **Low Stock Alerts**: Products below their reorder point appear on a low-stock dashboard.

## Authentication & Roles

### Authentication

Authentication uses a **passwordless, email-based flow** with trusted browser cookies.

#### Long-Term Vision

1. The user enters their **email address** on the login screen.
2. The system sends an email containing a **6-digit numeric code**.
3. The user enters the code to verify their identity.
4. Upon successful verification, a **persistent cookie** is set in the browser, marking it as **trusted**.
5. On subsequent visits from the same browser, the cookie is detected and the user is **automatically logged in**.
6. If the cookie is missing or expired (e.g., new browser, cleared cookies), the full email-code flow is triggered again.

#### Current Implementation (Phase 1)

- Email verification is **not yet implemented** — there is no external email-sending system in place.
- For now, the user enters their **email address only** and is logged in immediately (no code, no email sent).
- A persistent trusted-browser **cookie** is still set, so automatic login on return visits works from the start.
- The email verification step will be added later as a drop-in enhancement without changing the cookie/trusted-browser mechanism.

#### Technical Notes

- The cookie should be **HttpOnly**, **Secure**, and use **SameSite=Strict** for security best practices.
- The cookie should contain or reference a **server-side session or token** — do not store user identity directly in the cookie.
- The backend should expose an endpoint to **validate the cookie** on page load and return the current user context (business, role, etc.).
- The login endpoint should verify that the email belongs to an existing user before setting the cookie.

### Roles

- **Viewer** — Read-only access to all data. Can view reports, contacts, orders, and inventory but cannot create or modify anything. Useful for accountants or stakeholders who need visibility without edit access.
- **Staff** — Can create and manage contacts, products, quotes, sales orders, purchase orders, and inventory operations. Cannot manage accounting entries, invoices, bills, or payments directly.
- **Manager** — Full access to all operational features including invoicing, bills, payments, and basic accounting (posting entries, running reports). Cannot modify the chart of accounts or business settings.
- **Admin** — Full access to everything including chart of accounts, business settings, user management, and all operational features.

## Features

### Global Search

A unified search bar in the top navigation bar that lets users quickly find records across the entire system.

- **Scope**: Searches across contacts, products, invoices, quotes, sales orders, purchase orders, bills, credit notes, and expenses.
- **Matching**: Searches by name, number (invoice number, SO number, PO number, SKU), and email. Uses case-insensitive prefix matching ("sum" matches "Summit Supply Co."). No full-text search engine required — use SQL `LIKE` or EF Core `Contains` queries.
- **API**: A single `/api/search?q=<query>` endpoint that returns results grouped by entity type. Each result includes the entity type, display name, a subtitle (e.g., invoice amount, contact company), and a link to the detail page. Limited to 5 results per entity type for fast response.
- **UI**: A search input in the top bar (right side, next to the notifications bell). As the user types (debounced, 300ms), a dropdown panel appears below the input showing results grouped by category (Contacts, Products, Invoices, etc.) with category headers. Clicking a result navigates to its detail page and closes the dropdown. Pressing Escape or clicking outside closes it. Show a "No results" message when the query matches nothing.
- **Keyboard Shortcut**: `Cmd+K` (Mac) / `Ctrl+K` (Windows) focuses the search bar from anywhere in the app.
- **Tenant Scoped**: Search results are always scoped to the current user's business.

### Dashboard

The main landing page after login. Provides a snapshot of the business's current financial state.

- **Accounts Receivable Summary**: Total outstanding invoices, total overdue, number of invoices due this week.
- **Accounts Payable Summary**: Total outstanding bills, total overdue, number of bills due this week.
- **Cash Position**: Current balance of all cash/bank accounts.
- **Revenue This Month**: Total invoiced amount for the current month vs. prior month.
- **Expenses This Month**: Total billed amount for the current month vs. prior month.
- **Low Stock Alerts**: Count of products below reorder point, with a link to the full list.
- **Recent Activity Feed**: The last 10 transactions (invoices sent, payments received, POs created, etc.) across all modules.
- All metrics are computed server-side and returned via dedicated API endpoints.

### Contact Management

- Users can **create, edit, search, and deactivate contacts**.
- Contacts can be filtered by type (Customer, Vendor, Both).
- Each contact has a detail page with tabs:
  - **Overview** — Contact info, credit limit, payment terms, notes.
  - **Transactions** — Chronological list of all quotes, sales orders, invoices, payments, purchase orders, and bills linked to this contact.
  - **Statements** — Generate a customer statement showing all invoice and payment activity for a date range, with a running balance. Exportable as PDF.

### Product & Service Catalog

- Users can **create, edit, search, and deactivate products**.
- Products can be filtered by type (Inventory Item, Non-Inventory, Service) and category.
- Each product has a detail page showing:
  - Pricing, tax behavior, preferred vendor.
  - Current stock levels (for Inventory Items) across all warehouses.
  - Transaction history — all sales order lines and purchase order lines referencing this product.

### Quoting

- Users can create quotes for customers, add line items from the product catalog, and apply discounts.
- Quotes can be sent to customers via email (notification provider abstraction; stubbed for now).
- Accepted quotes can be converted into sales orders with one action.
- Quote list view with filters for status, customer, and date range.

### Sales Order Workflow

The end-to-end sales lifecycle:

1. **Create** — A user creates a sales order (manually or converted from a quote) with customer, line items, and payment terms.
2. **Confirm** — The SO moves from Draft to Confirmed. Inventory Items on the order are reserved (reducing available stock).
3. **Fulfill** — When items ship, the user records fulfillment. Full or partial fulfillment is supported. Fulfillment decrements on-hand inventory and releases reservations.
4. **Invoice** — The user generates an invoice from the fulfilled SO. Partial invoicing is supported.
5. **Collect Payment** — The customer pays, and the payment is applied to the invoice.

### Purchase Order Workflow

The end-to-end purchasing lifecycle:

1. **Create** — A user creates a PO with vendor, line items, and expected delivery date. Can be triggered from low-stock alerts.
2. **Send** — The PO moves from Draft to Sent. Can be emailed to the vendor (notification provider; stubbed).
3. **Receive** — When items arrive, the user records receipt. Full or partial receiving is supported. Receiving increments on-hand inventory.
4. **Bill** — The vendor sends an invoice (bill). The user enters it and optionally links it to the PO for matching.
5. **Pay** — The user records payment against the bill.

### Invoicing

- Users can create invoices from sales orders or as standalone invoices.
- Auto-population of line items when created from a sales order.
- Invoices can be emailed to customers and exported as PDF.
- Payment application — record incoming payments and apply them to specific invoices.
- Aging report — see all outstanding invoices grouped by aging bucket (Current, 1-30 days, 31-60 days, 61-90 days, 90+ days).

### Recurring Invoices

- Users can create recurring invoice templates from any customer with line items and a schedule.
- Active recurring invoices are listed with their frequency, next invoice date, and status.
- Invoices are generated automatically when the next invoice date arrives (checked on each API request or via a background job).
- Users can pause, resume, edit, or cancel recurring invoices.

### Credit Notes

- Users can create credit notes against a customer, optionally linked to a specific invoice.
- Issued credit notes can be applied to outstanding invoices to reduce their balance.
- Unapplied credit balances are visible on the customer's profile.
- Credit notes appear in the customer's transaction history and in the AR aging report (as negative amounts).

### Expense Tracking

- Users can record one-off expenses with an amount, expense account, category, and optional receipt upload.
- Expenses can be optionally linked to a vendor contact.
- Expense list view with filters for date range, category, account, and vendor.
- Recurring expenses auto-create entries on schedule.
- Expenses appear in the P&L report under their respective expense accounts.

### Bill Management

- Users enter vendor bills as they arrive, optionally linking to a PO.
- Payment application — record outgoing payments and apply them to specific bills.
- Aging report — see all outstanding bills grouped by aging bucket.

### Inventory Management

- **Stock Dashboard** — Overview of all products with current stock levels, reserved quantities, and available quantities. Filterable by warehouse and category. Products below reorder point are highlighted.
- **Receive Stock** — Record goods received against a purchase order.
- **Fulfill Orders** — Record goods shipped against a sales order.
- **Adjustments** — Manual stock corrections with a required reason field.
- **Transfers** — Move stock between warehouses.
- **Movement History** — For each product, view a chronological log of all stock movements with type, quantity, reference document, and resulting balance.

### Accounting

- **Chart of Accounts** — View, create, edit, and deactivate accounts. System accounts cannot be deleted.
- **Journal Entries** — Create manual journal entries for adjustments or accruals. View all entries (manual and automated) with filtering by date, account, and source.
- **General Ledger** — For each account, view all journal entry lines in date order with a running balance.
- **Bank Reconciliation** — Mark transactions as reconciled against bank statements. Simple checkbox-based reconciliation — no bank feed integration.
- **Trial Balance** — A report showing all account balances (debit and credit totals) at a point in time. Must balance to zero.

### Reporting

All reports are generated server-side and returned as structured data for the frontend to render. Reports should also be exportable as PDF.

- **Profit & Loss (Income Statement)** — Revenue minus expenses for a date range, grouped by account. Supports monthly/quarterly/yearly periods with period-over-period comparison.
- **Balance Sheet** — Assets, liabilities, and equity at a point in time. Assets = Liabilities + Equity must balance.
- **Cash Flow Statement** — Cash inflows and outflows for a date range, categorized as Operating, Investing, and Financing activities (simplified — categorized by account sub-type).
- **Accounts Receivable Aging** — Outstanding customer invoices grouped by aging bucket with totals per customer.
- **Accounts Payable Aging** — Outstanding vendor bills grouped by aging bucket with totals per vendor.
- **Sales by Product** — Total quantity sold and revenue for each product in a date range.
- **Sales by Customer** — Total revenue from each customer in a date range.
- **Purchase by Vendor** — Total spending with each vendor in a date range.
- **Inventory Valuation** — Current stock value (quantity on hand × weighted average cost) for each product and warehouse.
- **Tax Summary** — Total tax collected on sales and total tax paid on purchases for a date range, with net tax liability.

### Notifications

- **Invoice Reminders** — Admins can send payment reminder emails for overdue invoices.
- **Quote Sent** — Customer receives the quote via email.
- **PO Sent** — Vendor receives the purchase order via email.
- **Low Stock Alert** — When a product drops below its reorder point, an in-app notification is generated for managers and admins.
- **Implementation** — Notifications should use a **provider abstraction** (interface) so the delivery mechanism can be swapped later (e.g., SendGrid, SMTP). For now, the implementation is stubbed out — no actual emails are sent. In-app notifications (low stock, overdue reminders) are stored in a notifications table and displayed in the app's notification bell.

## Technical Requirements

### Platform

- **.NET 10** — Target the latest .NET 10 framework for all backend services.
- Enable **nullable reference types** across all projects.
- Enforce formatting with `dotnet format` — configuration checked into the repository.

### Architecture

- Follow **clean architecture** principles with clear separation of concerns:
  - **Domain** — Core entities, value objects, enums, and business rules. No external dependencies.
  - **Application** — Use cases, interfaces, DTOs, and validation. Depends only on Domain.
  - **Infrastructure** — Data access, external services, and framework implementations. Implements Application interfaces.
  - **API** — ASP.NET Core Web API exposing RESTful endpoints. Thin controllers delegating to the Application layer. Must expose an **OpenAPI/Swagger** specification (see API Contract).
- **Project naming convention** — Use a consistent naming pattern for solution projects (e.g., `LedgerLine.Domain`, `LedgerLine.Application`, `LedgerLine.Infrastructure`, `LedgerLine.Api`, `LedgerLine.Web`). Each project maps to exactly one architectural layer so the agent always knows where to find and place code.

### Database

- Use **Entity Framework Core** with an **in-memory database** for now. A persistent database (e.g., SQL Server or PostgreSQL) can be swapped in later via configuration.
- Use **explicit Fluent API configuration** for all entity mappings — no data annotations or convention-based configuration. This keeps the domain entities clean and makes the mappings unambiguous for the AI agent.
- Key entities: Businesses, Users, Contacts (with Customer/Vendor tags), Products, Categories, Warehouses, Stock Levels, Stock Movements, Accounts (Chart of Accounts), Journal Entries, Journal Entry Lines, Quotes, Quote Line Items, Sales Orders, Sales Order Line Items, Fulfillments, Invoices, Invoice Line Items, Payments Received, Payment Applications, Recurring Invoice Templates, Credit Notes, Credit Note Line Items, Credit Note Applications, Expenses, Expense Categories, Expense Attachments, Purchase Orders, PO Line Items, Receipts, Bills, Bill Line Items, Payments Made, Bill Payment Applications, In-App Notifications.
- All entities carry a `BusinessId` foreign key for tenant isolation. Queries should be automatically scoped to the current user's business.

### Frontend

- Use **React with TypeScript** for the web frontend.
  - Use **Vite** as the build tool for fast development.
  - Use **React Router** for client-side routing.
  - Enable **TypeScript strict mode** for maximum type safety.
  - Use **shadcn/ui** as the component library for all UI elements (buttons, cards, tables, dialogs, forms, dropdowns, comboboxes, date pickers, etc.). Initialize with `npx shadcn@latest init` and add components as needed with `npx shadcn@latest add <component>`. shadcn/ui copies components into the project as source files — customize them when needed but prefer the defaults for consistency.
  - Use **Tailwind CSS** for all styling (required by shadcn/ui). Use utility classes directly — no separate CSS files or CSS-in-JS. Follow a mobile-first approach with Tailwind's responsive prefixes (`sm:`, `md:`, `lg:`).
  - Use **React Hook Form** with **Zod** for all forms. shadcn/ui's `<Form>` component is built on these — every form in the app should follow the same pattern: define a Zod schema, create a form with `useForm<z.infer<typeof schema>>`, and use shadcn `<FormField>` components. No ad-hoc `useState`-based form handling.
  - Use **Tanstack Query (React Query)** for all API data fetching and mutations. Every API call should go through `useQuery` or `useMutation` — no raw `useEffect` + `fetch` patterns. This provides consistent loading/error states, caching, and automatic refetching.
  - Use **Tanstack Table** for all data tables and grids (contact lists, product lists, invoice tables, journal entries, stock levels). shadcn/ui's `<DataTable>` component is built on Tanstack Table. Use it for sorting, filtering, and pagination.
  - Use **Zustand** for lightweight global state (auth context, current business, active fiscal period). Prefer Zustand stores over React Context for cross-cutting state.
  - Use **date-fns** for all date/time formatting, parsing, and manipulation. Do not use `moment.js` or raw `Date` methods.
  - Use **Lucide React** for all icons (bundled with shadcn/ui). Do not add other icon libraries.
  - Use **Recharts** for all dashboard charts and report visualizations (bar charts, line charts, pie charts). It integrates well with React and is straightforward to implement.
  - Components should use semantic HTML elements and `data-testid` attributes to enable reliable element selection by AI agents and automated tests.
  - Prefer simple, page-based navigation with clearly labeled forms and controls.
  - The application must be **fully responsive** and work well on both **desktop browsers** and **tablets**. The primary use case is desktop, but key views (dashboard, contact lookup, invoice creation) should be usable on tablets.

### UI & Design

The application should look like a modern, professional SaaS accounting tool — clean, spacious, and data-dense where needed. The following guidelines ensure the AI agent produces a cohesive UI without needing a designer.

#### Color & Theme

- Use a **neutral base** (white/light gray backgrounds, dark gray text) with a single **brand accent color** (teal, e.g., Tailwind's `teal-600`) for primary actions, active nav items, and links.
- Use semantic status colors consistently everywhere:
  - Green for Paid, Fulfilled, Received, Active, Posted.
  - Yellow/amber for Draft, Pending, Partially Paid, Partially Fulfilled.
  - Red for Overdue, Void, Cancelled, low stock alerts.
  - Blue for Sent, Confirmed, informational.
  - Gray for inactive, archived, or deactivated items.
- Financial amounts should use green for positive/credit and red for negative/debit in reports. Use monospaced or tabular figures for number columns so digits align vertically.

#### Layout

- **Desktop (≥1024px)**: Fixed left sidebar (240px) with navigation, content area fills remaining width. Sidebar shows the business name/logo at the top, nav links organized by section in the middle, and the current user's name/role at the bottom.
- **Tablet (768–1023px)**: Collapsible sidebar — collapsed to icons by default, expands on hover or tap.
- **Mobile (<768px)**: Not a primary target, but basic navigation should still work — use a hamburger menu for nav access.
- All pages should have a max content width (e.g., `max-w-7xl`) centered on wide screens so content doesn't stretch uncomfortably on ultrawide monitors.

#### Components & Patterns

- **Cards**: Use cards (white background, subtle border or shadow, rounded corners) as the primary container for content sections — dashboard metric tiles, contact profiles, order summaries.
- **Tables**: Use clean, striped tables for list views (contacts, products, invoices, journal entries). Include column headers, hover highlighting, sortable columns, and pagination. Number columns should be right-aligned. On smaller screens, less important columns can be hidden.
- **Forms**: Labels above inputs. Inputs should be full-width within their container. Group related fields visually (e.g., billing address fields together). Use inline validation messages (red text below the field). Primary submit button is the accent color; secondary/cancel buttons are neutral.
- **Line Item Editors**: Quotes, sales orders, invoices, POs, bills, and journal entries all share a common line-item editing pattern — a table of rows where each row is a line item. Include an "Add Line" button below the table. Each row has a delete button. Show subtotal, tax, and total below the line items. Use a combobox (searchable dropdown) for product/account selection in line items.
- **Buttons**: Three tiers — primary (accent color, solid), secondary (outlined or light background), and destructive (red). Minimum tap target of 44×44px.
- **Modals/Dialogs**: Use for confirmations (void invoice, delete contact) and quick actions (apply payment to invoices). Keep modals focused — one task per modal.
- **Empty States**: Every list view should have a friendly empty state (icon + message + call-to-action button, e.g., "No invoices yet — create your first invoice").
- **Loading States**: Show skeleton loaders (pulsing placeholder shapes) for page content while API calls are in flight. Never show a blank page.
- **Error States**: API errors should show an inline error banner with a retry button — not a full-page error.
- **Toast Notifications**: Use brief toast messages (bottom-right) for action confirmations ("Invoice created", "Payment recorded", "Stock adjusted").

#### Document Views (Invoices, Quotes, POs)

- When viewing a finalized document (sent invoice, accepted quote, sent PO), show a clean, print-ready preview layout that mirrors the PDF output — company branding at top, recipient info, line items table, totals, terms. Include action buttons (Email, Download PDF, Record Payment) in a toolbar above the preview.
- When editing a draft, use the standard form layout with editable line items.

#### Report Views

- Reports should render as clean data tables with summary rows. Use alternating row colors for readability.
- Include a date range picker at the top of each report.
- Bar/line charts should appear above the data table for visual reports (P&L trend, revenue by month).
- Reports should have a "Download PDF" button.

#### Typography & Spacing

- Use Tailwind's default font stack (system fonts). No custom web fonts.
- Use consistent heading sizes: page titles `text-2xl font-bold`, section headings `text-lg font-semibold`, card titles `text-base font-medium`.
- Use Tailwind's spacing scale consistently — `p-4` / `p-6` for card padding, `gap-4` / `gap-6` for grid gaps, `space-y-4` for stacked elements.
- Use `font-mono` or tabular-nums for financial figures so numbers align properly in columns.

### API Contract

- The ASP.NET Core API should expose an **OpenAPI/Swagger** specification.
- Use an **auto-generated TypeScript API client** (e.g., via `openapi-typescript-codegen` or similar) so the frontend always matches the backend contract. This eliminates manual API wiring and reduces errors when the API changes.
- The generated client should be checked into the repository so changes are visible in diffs.

### PDF Generation

- Use a **PDF generation abstraction** (interface) so the rendering library can be swapped later.
- For now, use a lightweight library (e.g., QuestPDF or similar) to generate PDFs server-side.
- PDFs are needed for: invoices, quotes, purchase orders, customer statements, and all accounting reports.
- Each PDF should include the business's branding (name, logo, address, phone) in the header.

### Seed Data

- The app should start with seed data for development/demo purposes:
  - Business: "Summit Supply Co." with address, tax rate of 7.5%, invoice prefix "SS-", PO prefix "PO-", Net 30 default terms.
  - Admin user: `admin@summitsupply.com` (belongs to "Summit Supply Co.")
  - Manager user: `manager@summitsupply.com`
  - Staff user: `staff@summitsupply.com`
  - Chart of accounts populated with standard small-business accounts (Cash, AR, AP, Inventory, Sales Revenue, COGS, Rent, Utilities, Supplies, Payroll, etc.).
  - 5 sample customer contacts, 3 sample vendor contacts.
  - 10 sample products (mix of Inventory Items, Non-Inventory Items, and Services) with categories.
  - 1 warehouse ("Main Warehouse") with initial stock for inventory products.
  - A few sample transactions: 2 invoices (1 paid, 1 outstanding), 1 bill (outstanding), 1 completed sales order.
  - 1 active recurring invoice template (monthly, for a sample customer).
  - 3 sample expense categories (Travel, Office Supplies, Meals).
  - 2 sample expenses with different categories.

### Business Rules to Enforce

- **Double-entry accounting**: Every journal entry must have equal debit and credit totals. The API must reject unbalanced entries.
- **Posted entries are immutable**: Once a journal entry is posted, it cannot be edited — only reversed with a new correcting entry.
- **Invoice/bill status automation**: Invoice and bill statuses (Partially Paid, Paid, Overdue) must update automatically when payments are applied or due dates pass.
- **Inventory reservation**: Confirming a sales order reserves inventory. If available stock is insufficient, the API warns but allows the order (backorder scenario).
- **Fulfillment decrements stock**: Recording fulfillment on a sales order decreases on-hand inventory and releases the corresponding reservation.
- **Receiving increments stock**: Recording receipt on a purchase order increases on-hand inventory.
- **Credit limit warnings**: When creating a sales order for a customer with a credit limit, the API checks whether the order total plus existing outstanding AR would exceed the limit. If so, it returns a warning (but allows the order).
- **Cascading status updates**: Voiding an invoice reverses its journal entry automatically. Cancelling a sales order releases all reservations.
- **Credit note limits**: A credit note's total cannot exceed the linked invoice's total. When applied to invoices, the applied amount cannot exceed the credit note's remaining balance.
- **Recurring invoice generation**: Recurring invoices should generate new invoices when the next invoice date is on or before today. Generation is idempotent — if the invoice for a period already exists, it is not duplicated.
- **Fiscal year boundaries**: Reports respect the business's configured fiscal year start month.
- **Weighted average cost**: When inventory is received at a new cost, the system recalculates the weighted average cost for that product. Fulfillments use the current average cost for COGS journal entries.
- **Three-way matching**: When a bill is linked to a PO, the system highlights discrepancies in quantities or amounts between the PO, receipt, and bill.

### Testing

- Structure the solution so that Domain and Application layers can be **unit tested** independently of Infrastructure.
- API endpoints should support **integration testing** with a test database.
- Frontend pages should be testable via **Playwright** using `data-testid` attributes.
- Frontend components should have **React Testing Library** unit tests.
- All tests must be runnable from the command line with a single command (e.g., `dotnet test` for backend, `npm test` for frontend, `npx playwright test` for end-to-end).
- **Accounting tests are critical**: Unit tests must verify that every transaction type (invoice, payment, bill, fulfillment, adjustment) produces the correct journal entries with the correct account debits and credits.

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

- **Dashboard** — Business overview: AR/AP summaries, cash position, revenue/expense snapshot, low-stock alerts, recent activity.
- **Contacts** — Browse/search all contacts; filter by Customer/Vendor; drill into profiles for transactions, statements.
- **Products** — Browse/search products and services; filter by type and category; view stock and transaction history.
- **Sales**
  - **Quotes** — Create/manage customer quotes; convert to sales orders.
  - **Sales Orders** — Create/manage orders; fulfill and invoice.
  - **Invoices** — Create/manage invoices; record payments; aging report.
  - **Recurring Invoices** — Create/manage recurring invoice templates; view generation history.
  - **Credit Notes** — Issue credit notes; apply to invoices; track unapplied credits.
- **Expenses** — Record one-off expenses; upload receipts; manage categories; set up recurring expenses.
- **Purchasing**
  - **Purchase Orders** — Create/manage POs; record receipts.
  - **Bills** — Enter/manage vendor bills; record payments; aging report.
- **Inventory**
  - **Stock Levels** — Current stock across all warehouses with low-stock highlighting.
  - **Adjustments** — Record manual stock adjustments.
  - **Transfers** — Move stock between warehouses.
- **Accounting**
  - **Chart of Accounts** — View and manage accounts.
  - **Journal Entries** — View all entries; create manual entries.
  - **Bank Reconciliation** — Reconcile account transactions.
- **Reports**
  - Profit & Loss, Balance Sheet, Cash Flow, AR Aging, AP Aging, Sales by Product, Sales by Customer, Purchases by Vendor, Inventory Valuation, Tax Summary, Trial Balance.
- **Settings** — Business profile, tax rate, payment terms defaults, invoice/PO number prefixes, user management.
- **Notifications** — Bell icon in the top bar showing unread in-app notifications (low stock, overdue items).

### Manager Navigation

- Same as Admin except without Settings (no chart of accounts editing, no user management).

### Staff Navigation

- **Dashboard** — Same overview (read-only financials).
- **Contacts** — Full access.
- **Products** — Full access.
- **Sales** — Quotes and Sales Orders only (no direct invoice or payment access).
- **Purchasing** — Purchase Orders only (no bill or payment access).
- **Inventory** — Full access to stock operations.
- **Reports** — Sales by Product, Sales by Customer, Inventory Valuation only.

### Viewer Navigation

- Same sections as Staff but all views are read-only — no create, edit, or delete actions. Action buttons are hidden.

### Shared

- The top bar shows the business name/logo and the current user's name and role.
- Admin sees full nav; other roles see their permitted subset.
- **Desktop**: Fixed left sidebar with icon + label nav links, organized into collapsible sections (Sales, Purchasing, Inventory, Accounting, Reports).
- **Global search**: Top bar search input (right side) with `Cmd+K` / `Ctrl+K` keyboard shortcut. Typeahead results grouped by entity type.
- **Notifications bell**: Top-right corner (to the right of search) showing unread notification count. Click to see a dropdown of recent notifications.
