import os
import json
from flask import Flask, redirect, request, session, jsonify
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")


SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
# You need to set these environment variables in your deployment environment
BACKEND_BASE = os.environ.get("BACKEND_BASE_URL")   # e.g., https://your-api.onrender.com
STREAMLIT_BASE = os.environ.get("STREAMLIT_BASE_URL")  # e.g., https://your-app.streamlit.app

REDIRECT_URI = f"{BACKEND_BASE}/callback"

# Load the OAuth client from env (paste full JSON into GOOGLE_OAUTH_CLIENT_JSON)
CLIENT_JSON = json.loads(os.environ["GOOGLE_OAUTH_CLIENT_JSON"])
CLIENT_ID = CLIENT_JSON['web']['client_id']
CLIENT_SECRET = CLIENT_JSON['web']['client_secret']
TOKEN_URI = 'https://oauth2.googleapis.com/token'


@app.route('/login')
def login():
    flow = Flow.from_client_config(
        CLIENT_JSON,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'  # helps ensure refresh_token
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    state = session.get('state')
    if not state:
        return "Session state missing. Try logging in again.", 400

    flow = Flow.from_client_config(
        CLIENT_JSON,
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI
    )

    try:
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials
        session['access_token'] = creds.token
        session['refresh_token'] = creds.refresh_token

        # Redirect back to Streamlit (public URL), pass tokens via query params
        return redirect(
            f"{STREAMLIT_BASE}/?access_token={creds.token}&refresh_token={creds.refresh_token}"
        )
    except Exception as e:
        return f"Error during callback: {str(e)}", 500

@app.route('/emails')
def emails():
    access_token = session.get('access_token') or request.headers.get('Access-Token')
    refresh_token = session.get('refresh_token') or request.headers.get('Refresh-Token')

    if not access_token or not refresh_token:
        return jsonify({'error': 'Missing tokens'}), 401

    try:
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=TOKEN_URI,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES
        )

        if creds.expired:
            if creds.refresh_token:
                creds.refresh(Request())
                session['access_token'] = creds.token
            else:
                return jsonify({'error': 'Access token expired and no refresh token available'}), 401

        service = build('gmail', 'v1', credentials=creds)
        result = service.users().messages().list(
            userId='me',
            q=(
                'subject:"Thank you for Applying" OR '
                '"Thank you for your expression" OR '
                '"Thank you for applying" OR '
                '"Your application was sent" OR '
                '"Thank you for your application" OR '
                '"We have received your application"'
            ),
            maxResults=50
        ).execute()

        messages = result.get('messages', [])
        job_emails = []
        for msg in messages:
            msg_data = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            info = {'Subject': '', 'From': '', 'Date': ''}
            for h in headers:
                if h['name'] in info:
                    info[h['name']] = h['value']
            job_emails.append(info)

        return jsonify(job_emails)

    except Exception as e:
        if 'invalid_grant' in str(e):
            session.pop('access_token', None)
            session.pop('refresh_token', None)
            return jsonify({'error': 'invalid_grant - Please login again'}), 401
        return jsonify({'error': f'API error: {str(e)}'}), 500
    
@app.route('/logout')
def logout():
    session.pop('access_token', None)
    session.pop('refresh_token', None)
    return "Logged out. <a href='/login'>Login again</a>"

@app.route('/health')
def health():
    return 'ok', 200


if __name__ == '__main__':
    app.run(debug=True)
