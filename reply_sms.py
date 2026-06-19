import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import Flask and Twilio
try:
    from flask import Flask, request
    from twilio.twiml.messaging_response import MessagingResponse
except ImportError as err:
    print(f"Error: Required library missing - {err}")
    print("Please install required libraries by running: pip install flask twilio")
    sys.exit(1)

app = Flask(__name__)

@app.route("/sms", methods=['GET', 'POST'])
def incoming_sms():
    """Receive incoming SMS webhook, log to console, and auto-reply with TwiML."""
    # Twilio sends webhook data as a form/POST request
    from_number = request.values.get('From', 'Unknown Sender')
    to_number = request.values.get('To', 'Unknown Twilio Number')
    body = request.values.get('Body', '')

    print("\n==================================================")
    print(" RECEIVED INBOUND SMS REPLY (Part 2)")
    print("==================================================")
    print(f" From: {from_number}")
    print(f" To:   {to_number}")
    print(f" Body: '{body}'")
    print("==================================================")

    # Respond with TwiML auto-reply
    resp = MessagingResponse()
    resp.message("Thank you for contacting Retail RMS. Your response has been logged.")

    # Return standard XML response
    return str(resp), 200, {'Content-Type': 'application/xml'}

if __name__ == "__main__":
    # Load configuration
    port = int(os.getenv("PORT", 5000))
    print("==================================================")
    print(f" Starting local SMS Webhook listener on port {port}...")
    print("==================================================")
    print(" To test this script locally with ngrok:")
    print(" 1. In a new terminal, run: ngrok http 5000")
    print(" 2. Copy the public https URL (e.g., https://abc1234.ngrok-free.app)")
    print(" 3. Paste it as your Twilio phone number webhook URL, adding /sms to it:")
    print("    e.g., https://abc1234.ngrok-free.app/sms")
    print(" 4. Send an SMS reply to your Twilio number and watch the console below!")
    print("==================================================")
    
    app.run(debug=True, port=port)
