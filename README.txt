METAL FITNESS ARENA - GYM MEMBERSHIP & ACCESS CONTROL SYSTEM

This is the operational Flask + MySQL version. It is not a browser-only demo.

ARCHITECTURE
Browser -> Flask/Python -> MySQL

KEY FUNCTIONS
- Serial member IDs: 001, 002, 003 ... automatically.
- Optional manual member ID for authorised staff.
- Email is required when registering a member.
- A unique QR code is generated and automatically emailed to the member after registration.
- QR code can also be resent from the member profile.
- Real camera QR scanner for front-desk check-in.
- Access is granted only when membership is valid.
- Automatic expiry handling.
- Membership renewals and payment records.
- Staff roles: Administrator, Manager, Receptionist.
- Activity/audit log.
- Packages and prices.
- CSV member report.
- Bulk email, SMS and WhatsApp messaging for reminders, notices and announcements.
- Separate email and SMS/WhatsApp attempt history with provider errors.

IMPORTANT: The old attendance tables are preserved. New gym tables use the mfa_ prefix.

SETUP
1. Install Python 3.11+.
2. Make sure MySQL is running and the database named in MFA_DB_NAME already exists.
3. Copy .env.example to .env and enter your MySQL credentials.
4. Configure SMTP. For Gmail, create a Google App Password and put it in MFA_SMTP_PASSWORD.
5. For SMS, create a Termii account, fund it if required, and set MFA_TERMII_API_KEY and an approved sender ID in .env.
6. For WhatsApp, configure Meta WhatsApp Business Cloud API and set MFA_WHATSAPP_ACCESS_TOKEN and MFA_WHATSAPP_PHONE_NUMBER_ID in .env. To message people outside the 24-hour customer-service window, configure an approved template name with one body variable ({{1}}) in MFA_WHATSAPP_TEMPLATE_NAME.
7. Install dependencies:
   pip install -r requirements.txt
8. Start the system:
   python app.py
9. Open http://127.0.0.1:5000 in Chrome/Edge.

DEFAULT FIRST LOGIN
Username: admin
Password: password

Change the default admin password before real use. A password-change screen should be added before production if multiple staff are deployed.

CAMERA SCANNER
The web scanner uses html5-qrcode from the public CDN. Camera permission is required. Chrome/Edge allow camera access on localhost. For a LAN deployment, serve the application over HTTPS and consider hosting the scanner library locally.

EMAIL
Registration sends the QR code as a PNG attachment to the member's required email address. The Bulk Messaging page sends email to selected member emails, SMS through Termii, and WhatsApp through Meta Cloud API. Provider API keys belong only in the local .env file and must never be shared. SMS/WhatsApp provider charges may apply. A successful API response means the provider accepted the request; final delivery depends on the provider and recipient network. WhatsApp free-form messages generally require an open 24-hour customer-service window; approved templates are needed for outbound notices outside that window.

EMAIL PLACEHOLDERS
{name}       member full name
{member_id}  serial/member ID
{expiry_date} current membership expiry date

DATABASE
The application creates these tables automatically:
mfa_staff, mfa_packages, mfa_members, mfa_memberships, mfa_payments,
mfa_attendance, mfa_activity_log, mfa_member_sequence, mfa_email_log, mfa_message_log

The application does not delete members. Their payment and attendance history remains.
