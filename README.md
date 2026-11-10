# Employee Leave Management System (Team 12)

A beginner-friendly web application built with Python Flask, MySQL, HTML and CSS.

## Features
- Employee and manager registration/login
- Password hashing
- Employee leave balance dashboard
- Leave application with date and balance validation
- Manager approval/rejection
- Automatic balance deduction after approval
- Cancellation of pending or approved leave (approved leave is credited back)
- Status shown on employee dashboard

## Requirements
- Python 3.10+
- MySQL Server
- VS Code (recommended)

## Setup
1. Install Python and MySQL.
2. Open a terminal in this project folder.
3. Create and activate a virtual environment:
   - Windows: `py -m venv venv` then `venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv venv` then `source venv/bin/activate`
4. Install packages: `pip install -r requirements.txt`
5. Open MySQL Workbench or MySQL command line and run the full `schema.sql` file.
6. Set database credentials. The defaults are host `localhost`, user `root`, blank password, database `leave_management`.
   - Windows PowerShell example: `$env:DB_PASSWORD="your_mysql_password"`
   - macOS/Linux example: `export DB_PASSWORD="your_mysql_password"`
   - If needed, also set `DB_USER`, `DB_HOST`, and `DB_NAME`.
7. Run: `python app.py`
8. Open `http://127.0.0.1:5000` in your browser.

## First-time demo
1. Register one account with role **manager**.
2. Register another account with role **employee**.
3. Log in as employee, apply for leave.
4. Log out and log in as manager; approve or reject the request.
5. Log back in as employee to see the updated status and balance.

## Important notes
- This is an academic demonstration project, not a production HR system.
- For a real organization, manager accounts should be created/assigned by an administrator, not self-selected during public registration.
- The demo counts calendar days (including weekends). Change the day calculation if your institution requires working days only.
- Notifications are displayed as status updates on the employee dashboard; email/SMS integration is not included.
- Set a strong `SECRET_KEY` and disable Flask debug mode before any real deployment.
