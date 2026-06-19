import os
import sys
import argparse
from dotenv import load_dotenv

# Try to import Twilio Client
try:
    from twilio.rest import Client
except ImportError:
    print("Error: Twilio helper library is not installed.")
    print("Please run: pip install twilio")
    sys.exit(1)

def main():
    # Load environment variables from .env
    load_dotenv()

    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    from_number = os.getenv('TWILIO_PHONE_NUMBER')

    print("==================================================")
    print(" Twilio SMS Sender Tool (Part 1)")
    print("==================================================")

    # Check if .env contains required Twilio configuration
    if not all([account_sid, auth_token, from_number]):
        print("Error: Missing Twilio credentials in your .env file.")
        print("Please configure these keys in .env:")
        print("  TWILIO_ACCOUNT_SID")
        print("  TWILIO_AUTH_TOKEN")
        print("  TWILIO_PHONE_NUMBER")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Send an SMS using Twilio.")
    parser.add_argument("--to", help="The recipient phone number (E.164 format, e.g., +1234567890)")
    parser.add_argument("--message", help="The message body to send")
    args = parser.parse_args()

    to_number = args.to
    if not to_number:
        to_number = input("Enter recipient phone number (press Enter for +254701266217): ").strip()
        if not to_number:
            to_number = "+254701266217"

    message_body = args.message
    if not message_body:
        message_body = input("Enter message body (press Enter for default): ").strip()
        if not message_body:
            message_body = "Retail RMS: Your purchase issue has been resolved. Please let us know if you need anything else!"

    # Basic E.164 check warning
    if not to_number.startswith('+'):
        print("Warning: Phone numbers should ideally be in E.164 format (starting with '+').")

    try:
        print("\nInitializing Twilio Client...")
        client = Client(account_sid, auth_token)
        # Convert to WhatsApp format
        twilio_from = from_number
        if twilio_from == '+17656271910' or not twilio_from:
            twilio_from = 'whatsapp:+14155238886'
        elif not twilio_from.startswith('whatsapp:'):
            twilio_from = f"whatsapp:{twilio_from}"
        
        twilio_to = to_number
        if not twilio_to.startswith('whatsapp:'):
            twilio_to = f"whatsapp:{twilio_to}"

        print(f"Sending message to: {twilio_to}")
        print(f"From Twilio number: {twilio_from}")
        print(f"Message body: '{message_body}'")
        
        message = client.messages.create(
            body=message_body,
            from_=twilio_from,
            to=twilio_to
        )
        print("\n==================================================")
        print(" SUCCESS! SMS Dispatched Successfully.")
        print(f" Message SID: {message.sid}")
        print(f" Status:      {message.status}")
        print("==================================================")
    except Exception as e:
        print("\n==================================================")
        print(f" ERROR: Failed to send SMS.")
        print(f" Detail: {str(e)}")
        print("==================================================")
        sys.exit(1)

if __name__ == "__main__":
    main()
