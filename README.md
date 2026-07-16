# Company Map

Local Django app for mapping company accounts and storing account research.

## Run it

```bash
python3 manage.py runserver
```

Open <http://127.0.0.1:8000/>.

## Local with Neon

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Copy `.env.example` to `.env.local`, set `DATABASE_URL` to your Neon connection string, then run:

```bash
python3 manage.py migrate
python3 manage.py loaddata companymap_seed.json
python3 manage.py runserver
```

Unset `DATABASE_URL` to use local SQLite again.

## Useful commands

```bash
python3 manage.py test
python3 manage.py check
```

Import companies from CSV:

```bash
python3 manage.py import_companies sfaccts_research.csv
```

Use `--clear` to replace the existing map data:

```bash
python3 manage.py import_companies path/to/companies.csv --clear
```

CSV columns:

```csv
name,url,domain,address,city,state_code,state_name,country,postal_code,latitude,longitude,funding_data,revenue_data,decision_makers,notes
```

`name` is required. `latitude` and `longitude` are recommended; if they are blank, the importer uses built-in centroids for common cities. It also accepts Apollo/Salesforce account exports like `sfaccts_research.csv`.

## Deploy to Vercel + Neon

Create a Neon project and add these Vercel environment variables:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require
DJANGO_SECRET_KEY=<generated-secret>
DEBUG=False
ALLOWED_HOSTS=.vercel.app
CSRF_TRUSTED_ORIGINS=https://*.vercel.app
```

Before deploying, create the Neon schema and load data from your machine:

```bash
export DATABASE_URL='postgresql://USER:PASSWORD@HOST/DB?sslmode=require'
python3 manage.py migrate
python3 manage.py loaddata companymap_seed.json
```

Then import the GitHub repo into Vercel. Vercel detects `manage.py`, uses `emailcounter/wsgi.py`, and collects static files during the build.
