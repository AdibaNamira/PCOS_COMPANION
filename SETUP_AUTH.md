# Auth update — setup

## 1. Copy files in

Drop these into your project root, replacing `app.py`:

    app.py            (modified — auth wiring)
    auth.py           (new — routes + login_required)
    auth_store.py     (new — users, passwords, 2FA codes)
    chat_store.py     (new — chat history per user)
    mailer.py         (new — sends the code by email)
    templates/login.html   (new — create the templates/ folder)

No new pip packages needed. Werkzeug ships with Flask, smtplib is stdlib.

## 2. Add to your .env

Generate a secret key:

    python -c "import secrets; print(secrets.token_hex(32))"

Then add to .env:

    FLASK_SECRET_KEY=paste_the_generated_value_here

The app refuses to start without it — that's deliberate. A default or
missing key would let anyone forge a logged-in session.

## 3. Run

    python app.py

Visit http://127.0.0.1:5000 — you'll be redirected to /login.
Create an account. The 2FA code prints in your VS Code terminal.

## 4. Real email (optional, later)

Add to .env once you want codes actually emailed:

    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=465
    SMTP_USERNAME=youraddress@gmail.com
    SMTP_PASSWORD=your_16_char_app_password
    SMTP_FROM=youraddress@gmail.com

Gmail needs an App Password (Google Account > Security > 2-Step
Verification > App passwords). Your normal password will not work.

Until these are set, the code prints to the console and login still
works — so you can build the whole flow before touching email setup.

## 5. Update .gitignore

    .venv/
    .env
    __pycache__/
    cycle_data.db
    logs/
    feedback/

cycle_data.db now holds accounts, password hashes, health conversations
and cycle data. It must never reach a repo.

## New routes

    GET  /login             login/signup page
    POST /signup            create account -> 2FA step
    POST /login             check password -> 2FA step
    POST /verify            check code -> logged in
    POST /resend            new code
    POST /logout            clear session
    GET  /me                {authenticated, email}
    GET  /history           this user's past conversation
    POST /delete_my_data    erase this user's chats + cycle data

/, /chat, /cycle_status, /cycle_log and /feedback now require login.
