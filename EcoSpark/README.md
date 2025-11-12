# EcoSpark — E‑Waste Finder

EcoSpark is a Django-based web application that helps users discover certified e-waste recycling centers, learn about hazardous components, estimate recoverable value from devices, request pickups/community drives, and engage through gamified challenges and credits.

This README provides setup steps, an overview of features, and quick developer notes.

---

## Features

- Search and map of recycling centers (Google Places / Yelp integration fallback)
- AI-assisted education: component hazards, reuse vs recycle decision, daily eco tips, quizzes
- Value estimator for recoverable metals (gold, copper, silver)
- Credits system (UserCredit model) for user engagement
- Pickup scheduling (Pickup model) and admin management
- Gamified challenges (Challenge + ChallengeCompletion models) with per-user persistence
- Admin site to manage centers, devices, pickups, challenges

---

## Quick start (development)

Requirements: Python 3.10+ (use the virtualenv in this repo or create a new one)

1. Create and activate a virtual environment

   Windows PowerShell:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies

   ```powershell
   pip install -r requirements.txt
   ```

3. Configure environment

   - Create a `.env` in the project root for secrets (DO NOT commit it)
   - Example variables you may want:
     - `DJANGO_SECRET_KEY=your-secret`
     - `DATABASE_URL=sqlite:///db.sqlite3`
     - `GOOGLE_MAPS_API_KEY=`
     - `YELP_API_KEY=`

4. Run migrations and create a superuser

   ```powershell
   python manage.py makemigrations
   python manage.py migrate
   python manage.py createsuperuser
   ```

5. Run the development server

   ```powershell
   python manage.py runserver
   ```

6. Open the site at http://127.0.0.1:8000/ and admin at http://127.0.0.1:8000/admin/

---

## Project structure (high level)

- `core/` — main Django app with models, views, templates, static files
- `EcoSpark/` — Django project settings, wsgi/asgi
- `manage.py` — Django CLI

Key models: `RecyclingCenter`, `Device`, `UserCredit`, `Pickup`, `Challenge`, `ChallengeCompletion`.

---

## Deployment notes

- Use a production WSGI/ASGI server (gunicorn/uvicorn + nginx). Do not use Django dev server in production.
- Configure static files collection and a stable database (Postgres recommended).
- Do not commit `.env` or any API keys. Use environment variables or a secure secrets manager.

---

## Contributing

- Fork the repository and make feature branches.
- Open PRs against `main` branch.
- Keep migrations tidy: run `makemigrations` locally and commit the generated migration files.

---

## License

This repository includes a permissive MIT license by default. Replace if you need a different license.

---

If you want, I can also:

- Add a `CONTRIBUTING.md` template and `CODE_OF_CONDUCT.md`.
- Create `.env.example` with variable names.
- Upload the current repository to GitHub for you (if you provide a remote URL).
