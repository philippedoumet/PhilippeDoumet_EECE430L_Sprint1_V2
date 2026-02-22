# USD ↔ LBP Exchange Platform (EECE 430L Sprint 1)

This is a comprehensive FastAPI-based currency exchange platform featuring a real-time P2P marketplace, automated rate analytics, multi-factor authentication (MFA), and role-based access control (RBAC).

## Getting Started

### 1. Backend Environment Setup

Navigate to the backend directory:
```bash
cd PHILIPPEDOUMET_SPRINT1_202303965/exchange-app/backend


Create a virtual environment:
python -m venv .venv


Activate the environment:

Windows: .venv\Scripts\activate

Ubuntu/macOS: source .venv/bin/activate

Install dependencies: 
pip install -r requirements.txt

3. Database Initialization
The application uses SQLite for simplicity.

Initial Setup: The database (exchange.db) is automatically created when the server starts for the first time.

Resetting: If you modify models (e.g., adding balances or MFA fields), delete the exchange.db file and restart the server to rebuild the schema.

4. Running the Server
Run the application using Uvicorn with auto-reload enabled:

Bash
uvicorn app.main:app --reload --reload-dir app

The API will be available at http://127.0.0.1:8000.


Testing the Endpoints
1. Authentication & MFA
Registration: Open the Dashboard, enter email/password, and check "Register as System Admin" for full privileges.

MFA Login: Enter credentials. A browser prompt will appear; enter the 6-digit code sent to your email to proceed.

2. Real-Time Transaction Validation (Atomic Swap)
Wallet Balances: Users start with $10,000 USD and 1B LBP.

Validation: Attempt a transaction exceeding your balance; the system returns a 400 Bad Request.

Atomicity: Transactions ensure balance updates and record creation succeed or fail together.

3. P2P Marketplace & Escrow
Escrow: Posting a "SELL" offer locks the funds from your wallet immediately.

Cancellation: Cancel an open offer to have the escrowed funds refunded.

Acceptance: Accepting an offer triggers a real-time swap between the maker and taker.

4. Exchange Rate Analytics & Graphs
Stats: View min, max, average, and percentage change over hourly/daily intervals.

History: The system provides graph-ready time-series data for the selected range.

5. Watchlist & Notifications
Watchlist: Save specific rate thresholds or currency directions for tracking.

Notifications: Receive in-app updates for alert triggers, trade completions, and status changes.

6. Admin Panel & Moderation
Moderation: Admins can view all users and suspend or ban accounts to block API access.

Aggregated Reports: View total platform volume and identify the most active users.

Audit Trail: Access immutable logs for logins, trades, and system modifications.

7. Rate Limiting
Abuse Prevention: Attempting more than 5 requests per minute on sensitive endpoints (Login, Transactions) triggers a 429 Too Many Requests error.

8. Data Management & Export
CSV Export: Generate a downloadable history of all personal transactions.

Backups: Admins can trigger manual backups (exchange_backup.db) and restore system data.


Project Structure
/backend
    /app
        /auth.py        # JWT & RBAC Logic
        /db.py          # SQLAlchemy Engine
        /email_utils.py # SMTP OTP/Alert Logic
        /main.py        # API Routes & Rate Limiter
        /models.py      # Database Schema
        /schemas.py     # Pydantic Validation
        /stats.py       # Analytics Calculations
    /exchange.db        # SQLite Database
/frontend
    /index.html         # Single-page dynamic UI