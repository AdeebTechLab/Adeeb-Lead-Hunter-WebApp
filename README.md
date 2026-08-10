# Adeeb Lead Hunter

Production-oriented AI sales-intelligence and CRM platform for discovering, qualifying, auditing and managing business leads in Pakistan.

## Stack

- **Frontend:** React, TypeScript, Vite
- **API:** FastAPI
- **Database:** MongoDB / MongoDB Atlas
- **Images:** Cloudinary
- **Lead sources:** Google Places (optional), Geoapify, OpenStreetMap, public business websites
- **Hosting:** Vercel frontend + Render API

## Production features

- Login and account registration with role-based access.
- Admin, Manager and User roles.
- Initial administrator created automatically on first API start.
- Required account fields: full name, email, password, CNIC and city.
- Optional profile image with center crop, zoom-only control and 1 MB limit.
- Cloudinary-backed profile image storage with server-side validation and metadata stripping.
- Real-time business search by niche, city and province.
- Contact enrichment from configured place APIs and public business websites.
- Website audit, lead score, service recommendation and sales opportunity summary.
- Complete cold-call, WhatsApp, email and LinkedIn outreach content.
- Qualified lead database, filters, CRM pipeline, notes, follow-ups, proposals and deal status.
- Activity logs, notifications, analytics, CSV and Excel export.
- Responsive light/dark interface with themed scrollbars and sidebar logout for every role.
- Safe provider fallback and user-facing errors without raw upstream traces.

## Repository structure

```text
ai-lead-hunter-production/
├── backend/
│   ├── app/
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── public/
│   ├── src/
│   ├── .env.example
│   └── vercel.json
├── render.yaml
└── README.md
```

## Local setup

### 1. Backend

Create a MongoDB database locally or use MongoDB Atlas, then:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env`. At minimum set your MongoDB URI and provider keys. If profile uploads will be tested, also add Cloudinary credentials.

Start the API:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open `http://localhost:5173`.

For the default development configuration, the initial administrator is:

```text
Email: admin@example.com
Password: Admin@123
```

The production configuration rejects that default password and placeholder CNIC. Set secure production values on Render before deployment.

## Account rules

Public signup always creates a normal **User** account. It cannot create Manager or Admin privileges. Only an Admin can create users with elevated roles or change roles.

CNIC values are normalized to `#####-#######-#` and stored uniquely. All signup fields are required except the profile photo.

Profile photos accept JPEG, PNG or WebP files up to 1 MB. The browser provides a centered square crop with a zoom control only. The API validates the file again, strips metadata, normalizes it to a 512×512 JPEG and uploads it to Cloudinary.

## Required production environment variables

Set these on the Render service:

```env
ENVIRONMENT=production
SECRET_KEY=<generated secret at least 32 characters>
MONGODB_URI=<MongoDB Atlas connection string>
MONGODB_DB=ai_lead_hunter
FRONTEND_ORIGINS=https://your-vercel-domain.vercel.app
ALLOW_PUBLIC_SIGNUP=true

DEFAULT_ADMIN_NAME=Admin User
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=<strong unique password>
DEFAULT_ADMIN_CNIC=<valid unique CNIC>
DEFAULT_ADMIN_CITY=Islamabad

CLOUDINARY_CLOUD_NAME=<cloud name>
CLOUDINARY_API_KEY=<api key>
CLOUDINARY_API_SECRET=<api secret>

GEOAPIFY_API_KEY=<key>
GOOGLE_PLACES_API_KEY=<optional key>
PUBLIC_DATA_USER_AGENT=AILeadHunter/1.0 (contact: you@example.com)
PUBLIC_DATA_REFERER=https://your-vercel-domain.vercel.app
```

Never place MongoDB, Cloudinary, Geoapify or Google API secrets in the frontend environment.

## MongoDB Atlas

Create an Atlas cluster and database user, allow network access for your deployment, then copy the application connection string into `MONGODB_URI` on Render. The API creates required indexes automatically, including unique email/CNIC indexes and lead-search indexes.

## Cloudinary

Create a Cloudinary account and copy the cloud name, API key and API secret into Render environment variables. The API secret stays on Render; profile images are uploaded by the FastAPI backend and only the resulting secure image URL is stored in MongoDB.

## Lead provider configuration

**Automatic** source priority:

1. Google Places when configured.
2. Geoapify when configured and the niche mapping is supported.
3. OpenStreetMap fallback.
4. Public contact discovery from the business's own website.

For reliable production contact coverage, configure at least Geoapify. Google Places can be added for richer official phone, website, rating and Maps data. Missing contact details are never invented.

## Render deployment

1. Push the project to GitHub.
2. In Render, create a Blueprint from `render.yaml`, or create a Python Web Service with root directory `backend`.
3. Add every required secret/environment variable shown above.
4. Deploy and confirm `https://<render-service>/health` returns `status: ok`.
5. Copy the Render API URL for the Vercel configuration.

The production start command is already defined in `render.yaml`.

## Vercel deployment

1. Import the same repository into Vercel.
2. Set **Root Directory** to `frontend`.
3. Add:

```env
VITE_API_URL=https://your-render-service.onrender.com/api
```

4. Deploy.
5. Copy the final Vercel domain back into Render as `FRONTEND_ORIGINS` and `PUBLIC_DATA_REFERER`, then redeploy the API.

`frontend/vercel.json` contains the SPA rewrite required for direct navigation to routes such as `/leads`, `/crm` and `/settings`.

## Production administrator

On API startup, the backend checks for `DEFAULT_ADMIN_EMAIL`. If no matching account exists, it creates the administrator using the configured name, password, CNIC and city. It does not overwrite an existing administrator on later restarts.

## Validation

Backend test suite:

```powershell
cd backend
$env:PYTHONPATH="."
pytest -q
```

Frontend validation:

```powershell
cd frontend
npm install
npm run build
```

Before going live, test login, signup, profile upload, all three roles, lead search, lead import, audit, CRM updates, exports and logout on the deployed Vercel/Render URLs.

## Security notes

- Production startup rejects the default administrator password and placeholder CNIC.
- API secrets remain server-side.
- Public signup cannot self-assign privileged roles.
- Passwords are stored as salted PBKDF2 hashes.
- MongoDB email and CNIC uniqueness are enforced at database level.
- Uploaded profile images are validated and normalized before Cloudinary upload.
- CORS is restricted to `FRONTEND_ORIGINS`.
- API and frontend responses include baseline security headers.
- Raw provider errors and upstream URLs are not exposed to users.
