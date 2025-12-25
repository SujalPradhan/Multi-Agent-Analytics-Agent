#!/usr/bin/env python3
"""
Hugging Face Spaces startup script.
Handles credentials from environment variables before starting the app.
"""

import os
import sys
import base64
import json

def setup_credentials():
    """
    Set up Google credentials from HF Secrets.
    
    The credentials should be stored as a base64-encoded JSON string
    in the GOOGLE_CREDENTIALS_BASE64 secret, OR as raw JSON in 
    GOOGLE_CREDENTIALS_JSON secret.
    """
    credentials_path = "credentials.json"
    
    # Skip if credentials file already exists
    if os.path.exists(credentials_path):
        print(f"✓ Credentials file already exists: {credentials_path}")
        return True
    
    # Try base64-encoded credentials first
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode("utf-8")
            with open(credentials_path, "w") as f:
                f.write(creds_json)
            print(f"✓ Created credentials from GOOGLE_CREDENTIALS_BASE64")
            return True
        except Exception as e:
            print(f"✗ Failed to decode GOOGLE_CREDENTIALS_BASE64: {e}")
    
    # Try raw JSON credentials
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        try:
            # Validate it's valid JSON
            json.loads(creds_json)
            with open(credentials_path, "w") as f:
                f.write(creds_json)
            print(f"✓ Created credentials from GOOGLE_CREDENTIALS_JSON")
            return True
        except Exception as e:
            print(f"✗ Failed to parse GOOGLE_CREDENTIALS_JSON: {e}")
    
    print("⚠ No Google credentials found in environment.")
    print("  Set GOOGLE_CREDENTIALS_BASE64 or GOOGLE_CREDENTIALS_JSON in HF Secrets.")
    print("  The app will start but Google API calls will fail.")
    return False


def main():
    """Main entry point for HF Spaces."""
    print("=" * 50)
    print("Spike AI - Starting on Hugging Face Spaces")
    print("=" * 50)
    
    # Set up credentials from secrets
    setup_credentials()
    
    # Import and run the main app
    print("\nStarting FastAPI server...")
    from main import run_server
    run_server()


if __name__ == "__main__":
    main()
