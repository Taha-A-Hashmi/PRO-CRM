# Hospital CRM (PRO System)

## Local Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Run MongoDB locally.
3. Run the app: `python app.py`
4. Go to http://127.0.0.1:5000

## Environment

- `MONGO_URI`: Mongo connection string
- `SECRET_KEY`: Flask secret key
- `GMAIL_USER`: Gmail address used to send reset emails
- `GMAIL_APP_PASSWORD`: App password for the sender account
- `PASSWORD_RESET_EXPIRY_MINUTES` (optional): Token expiry window, defaults to 30
