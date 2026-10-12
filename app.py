import os, io, csv, re, smtplib, ssl, json, urllib.request, urllib.error
from pathlib import Path
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request, session, send_file, render_template
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"), override=True)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv('MFA_SECRET_KEY', 'change-this-secret-key')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DB = dict(
    host=os.getenv('MFA_DB_HOST', 'localhost'),
    port=int(os.getenv('MFA_DB_PORT', '3306')),
    user=os.getenv('MFA_DB_USER', 'MFA_User'),
    password=os.getenv('MFA_DB_PASSWORD', ''),
    database=os.getenv('MFA_DB_NAME', 'MFA_GYM_REPORT')
)

SMTP = dict(
    host=os.getenv('MFA_SMTP_HOST', 'smtp.gmail.com'),
    port=int(os.getenv('MFA_SMTP_PORT', '465')),
    user=os.getenv('MFA_SMTP_USER', '') or os.getenv('MFA_SMTP_FROM', ''),
    password=os.getenv('MFA_SMTP_PASSWORD', ''),
    from_email=os.getenv('MFA_SMTP_FROM', '') or os.getenv('MFA_SMTP_USER', ''),
    from_name=os.getenv('MFA_SMTP_FROM_NAME', 'Metal Fitness Arena'),
)

TERMII = dict(api_key=os.getenv('MFA_TERMII_API_KEY', ''), sender_id=os.getenv('MFA_TERMII_SENDER_ID', 'MFA'), channel=os.getenv('MFA_TERMII_CHANNEL', 'dnd'), base_url=os.getenv('MFA_TERMII_BASE_URL', 'https://api.ng.termii.com/api/sms/send'))
WHATSAPP = dict(token=os.getenv('MFA_WHATSAPP_ACCESS_TOKEN', ''), phone_number_id=os.getenv('MFA_WHATSAPP_PHONE_NUMBER_ID', ''), api_version=os.getenv('MFA_WHATSAPP_API_VERSION', 'v23.0'), template_name=os.getenv('MFA_WHATSAPP_TEMPLATE_NAME', ''), template_language=os.getenv('MFA_WHATSAPP_TEMPLATE_LANGUAGE', 'en'))



def db():
    return mysql.connector.connect(**DB)


def query(sql, params=(), one=False, commit=False):
    con = db()
    cur = con.cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        if commit:
            con.commit()
            return cur.lastrowid
        rows = cur.fetchall()
        return rows[0] if one and rows else (None if one else rows)
    finally:
        cur.close()
        con.close()


def init_db():
    con = db()
    cur = con.cursor(dictionary=True)
    statements = [
        '''CREATE TABLE IF NOT EXISTS mfa_staff (
            id INT AUTO_INCREMENT PRIMARY KEY, full_name VARCHAR(150) NOT NULL,
            username VARCHAR(80) UNIQUE NOT NULL, email VARCHAR(150), password_hash VARCHAR(255) NOT NULL,
            role ENUM('Administrator','Manager','Receptionist') NOT NULL DEFAULT 'Receptionist',
            status ENUM('active','disabled') NOT NULL DEFAULT 'active', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_packages (
            id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) UNIQUE NOT NULL, price DECIMAL(12,2) NOT NULL,
            duration_days INT NOT NULL, description VARCHAR(255), active TINYINT(1) DEFAULT 1
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_members (
            id INT AUTO_INCREMENT PRIMARY KEY, member_id VARCHAR(30) UNIQUE NOT NULL,
            qr_code VARCHAR(80) UNIQUE NOT NULL, full_name VARCHAR(150) NOT NULL, phone VARCHAR(30) NOT NULL,
            email VARCHAR(150) NOT NULL, gender VARCHAR(30), photo VARCHAR(255), emergency_contact VARCHAR(150),
            registration_date DATE NOT NULL, status ENUM('active','expired','suspended','inactive') NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_memberships (
            id INT AUTO_INCREMENT PRIMARY KEY, member_id INT NOT NULL, package_id INT NOT NULL,
            start_date DATE NOT NULL, expiry_date DATE NOT NULL, amount DECIMAL(12,2) NOT NULL, payment_id INT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(member_id) REFERENCES mfa_members(id), FOREIGN KEY(package_id) REFERENCES mfa_packages(id),
            INDEX(member_id, expiry_date)
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_payments (
            id INT AUTO_INCREMENT PRIMARY KEY, member_id INT NOT NULL, package_id INT NOT NULL,
            amount DECIMAL(12,2) NOT NULL, payment_date DATETIME NOT NULL,
            payment_method ENUM('Cash','Bank Transfer','POS','Online Payment') NOT NULL,
            payment_type ENUM('New Registration','Membership Renewal') NOT NULL, recorded_by INT NULL,
            FOREIGN KEY(member_id) REFERENCES mfa_members(id), FOREIGN KEY(package_id) REFERENCES mfa_packages(id),
            FOREIGN KEY(recorded_by) REFERENCES mfa_staff(id), INDEX(payment_date)
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_attendance (
            id INT AUTO_INCREMENT PRIMARY KEY, member_id INT NOT NULL, checkin_at DATETIME NOT NULL,
            status VARCHAR(30) NOT NULL, staff_id INT NULL, FOREIGN KEY(member_id) REFERENCES mfa_members(id),
            FOREIGN KEY(staff_id) REFERENCES mfa_staff(id), INDEX(checkin_at), INDEX(member_id, checkin_at)
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_activity_log (
            id INT AUTO_INCREMENT PRIMARY KEY, staff_id INT NULL, action VARCHAR(100) NOT NULL,
            details TEXT, created_at DATETIME NOT NULL, FOREIGN KEY(staff_id) REFERENCES mfa_staff(id), INDEX(created_at)
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_member_sequence (
            id TINYINT PRIMARY KEY, next_number INT NOT NULL
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_email_log (
            id INT AUTO_INCREMENT PRIMARY KEY, member_id INT NULL, recipient_email VARCHAR(190) NOT NULL,
            subject VARCHAR(255) NOT NULL, email_type VARCHAR(50) NOT NULL, status ENUM('sent','failed') NOT NULL,
            error_message TEXT NULL, sent_by INT NULL, sent_at DATETIME NOT NULL,
            FOREIGN KEY(member_id) REFERENCES mfa_members(id) ON DELETE SET NULL,
            FOREIGN KEY(sent_by) REFERENCES mfa_staff(id) ON DELETE SET NULL, INDEX(sent_at)
        )''',
        '''CREATE TABLE IF NOT EXISTS mfa_message_log (
            id INT AUTO_INCREMENT PRIMARY KEY, member_id INT NULL, channel VARCHAR(20) NOT NULL,
            recipient VARCHAR(40) NOT NULL, message_text TEXT NOT NULL, status ENUM('sent','failed') NOT NULL,
            provider_message_id VARCHAR(255) NULL, error_message TEXT NULL, sent_by INT NULL, sent_at DATETIME NOT NULL,
            FOREIGN KEY(member_id) REFERENCES mfa_members(id) ON DELETE SET NULL,
            FOREIGN KEY(sent_by) REFERENCES mfa_staff(id) ON DELETE SET NULL, INDEX(sent_at), INDEX(channel,status)
        )'''
    ]
    for s in statements:
        cur.execute(s)

    # Safe migration for installations created by the earlier connected build.
    try:
        cur.execute("ALTER TABLE mfa_members ADD COLUMN email VARCHAR(150) NULL")
    except mysql.connector.Error as e:
        if e.errno != 1060:
            raise

    cur.execute("UPDATE mfa_members SET email='unknown@invalid.local' WHERE email IS NULL OR TRIM(email)=''")
    try:
        cur.execute("ALTER TABLE mfa_members MODIFY COLUMN email VARCHAR(150) NOT NULL")
    except mysql.connector.Error:
        pass

    defaults = [
        ('Daily', 1000, 1, 'One day'), ('Weekly', 5000, 7, 'Seven days'),
        ('Monthly', 15000, 30, 'Thirty days'), ('3 Months', 40000, 90, 'Ninety days'),
        ('6 Months', 75000, 180, '180 days'), ('Annual', 130000, 365, '365 days')
    ]
    cur.executemany(
        'INSERT IGNORE INTO mfa_packages(name,price,duration_days,description) VALUES(%s,%s,%s,%s)', defaults
    )
    cur.execute('SELECT COUNT(*) AS c FROM mfa_staff')
    if cur.fetchone()['c'] == 0:
        cur.execute(
            'INSERT INTO mfa_staff(full_name,username,email,password_hash,role) VALUES(%s,%s,%s,%s,%s)',
            ('MFA Administrator', 'admin', '', generate_password_hash('password'), 'Administrator')
        )
    cur.execute('INSERT IGNORE INTO mfa_member_sequence(id,next_number) VALUES(1,1)')

    # Move the sequence ahead of any already-existing numeric member IDs.
    cur.execute("SELECT MAX(CAST(member_id AS UNSIGNED)) AS max_id FROM mfa_members WHERE member_id REGEXP '^[0-9]+$'")
    max_id = cur.fetchone()['max_id'] or 0
    cur.execute('SELECT next_number FROM mfa_member_sequence WHERE id=1')
    next_number = cur.fetchone()['next_number']
    if next_number <= max_id:
        cur.execute('UPDATE mfa_member_sequence SET next_number=%s WHERE id=1', (max_id + 1,))

    con.commit()
    cur.close()
    con.close()


def log(action, details=''):
    if session.get('staff_id'):
        query(
            'INSERT INTO mfa_activity_log(staff_id,action,details,created_at) VALUES(%s,%s,%s,NOW())',
            (session['staff_id'], action, details), commit=True
        )


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapped(*a, **kw):
            if not session.get('staff_id'):
                return jsonify(error='Authentication required'), 401
            if session.get('role') not in roles:
                return jsonify(error='Permission denied'), 403
            return fn(*a, **kw)
        return wrapped
    return deco


def refresh_expired():
    query(
        "UPDATE mfa_members m JOIN (SELECT member_id, MAX(expiry_date) expiry FROM mfa_memberships GROUP BY member_id) x "
        "ON x.member_id=m.id SET m.status='expired' WHERE x.expiry < CURDATE() AND m.status='active'",
        commit=True
    )


def current_membership(member_pk):
    return query(
        '''SELECT ms.*, p.name package_name, p.duration_days FROM mfa_memberships ms
           JOIN mfa_packages p ON p.id=ms.package_id
           WHERE ms.member_id=%s ORDER BY ms.expiry_date DESC, ms.id DESC LIMIT 1''',
        (member_pk,), one=True
    )


def generate_serial_member_id(cur, manual_id=None):
    if manual_id:
        value = str(manual_id).strip()
        if not re.fullmatch(r'[A-Za-z0-9-]{1,30}', value):
            raise ValueError('Manual member ID may contain only letters, numbers and hyphens.')
        cur.execute('SELECT id FROM mfa_members WHERE member_id=%s FOR UPDATE', (value,))
        if cur.fetchone():
            raise ValueError('That member ID is already in use.')
        numeric = int(value) if value.isdigit() else None
        if numeric is not None:
            cur.execute('UPDATE mfa_member_sequence SET next_number=GREATEST(next_number,%s) WHERE id=1', (numeric + 1,))
        return value

    cur.execute('SELECT next_number FROM mfa_member_sequence WHERE id=1 FOR UPDATE')
    row = cur.fetchone()
    n = row['next_number']
    while True:
        value = f'{n:03d}'
        cur.execute('SELECT id FROM mfa_members WHERE member_id=%s', (value,))
        if not cur.fetchone():
            break
        n += 1
    cur.execute('UPDATE mfa_member_sequence SET next_number=%s WHERE id=1', (n + 1,))
    return value


def qr_bytes(token):
    img = qrcode.make(token)
    b = io.BytesIO()
    img.save(b, 'PNG')
    return b.getvalue()


def smtp_configured():
    return bool(SMTP['host'] and SMTP['user'] and SMTP['password'] and SMTP['from_email'])


def send_mail(to_email, subject, body, attachment=None, attachment_name=None):
    if not smtp_configured():
        raise RuntimeError('Email is not configured. Add MFA_SMTP_USER, MFA_SMTP_PASSWORD and MFA_SMTP_FROM to .env.')
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{SMTP['from_name']} <{SMTP['from_email']}>"
    msg['To'] = to_email
    msg.set_content(body)
    if attachment:
        msg.add_attachment(attachment, maintype='image', subtype='png', filename=attachment_name or 'attachment.png')

    if SMTP['port'] == 465:
        with smtplib.SMTP_SSL(SMTP['host'], SMTP['port'], timeout=30) as server:
            server.login(SMTP['user'], SMTP['password'])
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP['host'], SMTP['port'], timeout=30) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(SMTP['user'], SMTP['password'])
            server.send_message(msg)


def phone_to_international(value):
    # Normalize Nigerian local numbers to international digits-only format.
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = "234" + digits[1:]
    elif len(digits) == 10:
        digits = "234" + digits
    if not (10 <= len(digits) <= 15):
        raise ValueError(f"Invalid phone number: {value}")
    return digits


def provider_post(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.dumps(json.loads(detail), ensure_ascii=False)
        except Exception:
            pass
        raise RuntimeError(f"Messaging provider returned HTTP {e.code}: {detail[:1000]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach messaging provider: {e.reason}")


def send_sms(phone, message):
    if not TERMII['api_key']:
        raise RuntimeError('SMS is not configured. Add MFA_TERMII_API_KEY and MFA_TERMII_SENDER_ID to .env.')
    result = provider_post(TERMII['base_url'], {
        'to': phone_to_international(phone), 'from': TERMII['sender_id'], 'sms': message,
        'type': 'plain', 'channel': TERMII['channel'], 'api_key': TERMII['api_key']
    })
    if result.get('code') and str(result.get('code')).lower() not in ('ok', '200', 'success'):
        raise RuntimeError(result.get('message') or str(result))
    return str(result.get('message_id') or result.get('messageId') or '')


def send_whatsapp(phone, message):
    if not WHATSAPP['token'] or not WHATSAPP['phone_number_id']:
        raise RuntimeError('WhatsApp is not configured. Add MFA_WHATSAPP_ACCESS_TOKEN and MFA_WHATSAPP_PHONE_NUMBER_ID to .env.')
    url = f"https://graph.facebook.com/{WHATSAPP['api_version']}/{WHATSAPP['phone_number_id']}/messages"
    payload = {'messaging_product': 'whatsapp', 'to': phone_to_international(phone)}
    if WHATSAPP['template_name']:
        # Configure an approved WhatsApp template with a single body variable ({{1}}).
        payload.update({'type': 'template', 'template': {'name': WHATSAPP['template_name'], 'language': {'code': WHATSAPP['template_language']}, 'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': message[:1024]}]}]}})
    else:
        # Free-form text is normally limited to the 24-hour customer-service window.
        payload.update({'type': 'text', 'text': {'body': message[:4096], 'preview_url': False}})
    result = provider_post(url, payload, {'Authorization': f"Bearer {WHATSAPP['token']}"})
    messages = result.get('messages') or []
    return str(messages[0].get('id', '')) if messages else ''


def message_log(member_pk, channel, recipient, message, status, error='', provider_id=''):
    query('''INSERT INTO mfa_message_log(member_id,channel,recipient,message_text,status,provider_message_id,error_message,sent_by,sent_at)
             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW())''',
          (member_pk, channel, recipient, message[:4000], status, provider_id[:255], error[:2000], session.get('staff_id')), commit=True)


def email_log(member_pk, recipient, subject, email_type, status, error=''):
    query(
        '''INSERT INTO mfa_email_log(member_id,recipient_email,subject,email_type,status,error_message,sent_by,sent_at)
           VALUES(%s,%s,%s,%s,%s,%s,%s,NOW())''',
        (member_pk, recipient, subject, email_type, status, error[:2000], session.get('staff_id')), commit=True
    )


@app.route('/')
def home():
    return render_template('index.html')


@app.post('/api/login')
def login():
    data = request.json or {}
    u = query('SELECT * FROM mfa_staff WHERE username=%s AND status="active"', (data.get('username', '').strip(),), one=True)
    if not u or not check_password_hash(u['password_hash'], data.get('password', '')):
        return jsonify(error='Invalid username or password'), 401
    session['staff_id'] = u['id']
    session['role'] = u['role']
    session['name'] = u['full_name']
    log('Staff login')
    return jsonify(name=u['full_name'], role=u['role'])


@app.post('/api/logout')
def logout():
    if session.get('staff_id'):
        log('Staff logout')
    session.clear()
    return jsonify(ok=True)


@app.get('/api/me')
def me():
    if not session.get('staff_id'):
        return jsonify(authenticated=False)
    return jsonify(authenticated=True, name=session['name'], role=session['role'])


@app.get('/api/dashboard')
@role_required('Administrator', 'Manager', 'Receptionist')
def dashboard():
    refresh_expired()
    total = query('SELECT COUNT(*) c FROM mfa_members', one=True)['c']
    active = query("SELECT COUNT(*) c FROM mfa_members WHERE status='active'", one=True)['c']
    expired = query("SELECT COUNT(*) c FROM mfa_members WHERE status='expired'", one=True)['c']
    today = query('SELECT COUNT(*) c FROM mfa_attendance WHERE DATE(checkin_at)=CURDATE()', one=True)['c']
    new_month = query("SELECT COUNT(*) c FROM mfa_members WHERE YEAR(registration_date)=YEAR(CURDATE()) AND MONTH(registration_date)=MONTH(CURDATE())", one=True)['c']
    renew_month = query("SELECT COUNT(*) c FROM mfa_payments WHERE payment_type='Membership Renewal' AND YEAR(payment_date)=YEAR(CURDATE()) AND MONTH(payment_date)=MONTH(CURDATE())", one=True)['c']
    revenue = query("SELECT COALESCE(SUM(amount),0) total FROM mfa_payments WHERE YEAR(payment_date)=YEAR(CURDATE()) AND MONTH(payment_date)=MONTH(CURDATE())", one=True)['total']
    expiring = query(
        '''SELECT m.member_id,m.full_name,m.email,m.status,ms.expiry_date,p.name package_name,
                  DATEDIFF(ms.expiry_date,CURDATE()) days_left
           FROM mfa_members m JOIN mfa_memberships ms ON ms.member_id=m.id JOIN mfa_packages p ON p.id=ms.package_id
           WHERE ms.id=(SELECT id FROM mfa_memberships WHERE member_id=m.id ORDER BY expiry_date DESC,id DESC LIMIT 1)
             AND ms.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(),INTERVAL 7 DAY)
           ORDER BY ms.expiry_date LIMIT 10''')
    recent = query("SELECT m.full_name,m.member_id,a.checkin_at FROM mfa_attendance a JOIN mfa_members m ON m.id=a.member_id ORDER BY a.checkin_at DESC LIMIT 10")
    registrations = query("SELECT full_name,member_id,registration_date FROM mfa_members ORDER BY registration_date DESC, id DESC LIMIT 8")
    payments = query("SELECT m.full_name,m.member_id,p.amount,p.payment_date,p.payment_type FROM mfa_payments p JOIN mfa_members m ON m.id=p.member_id ORDER BY p.payment_date DESC LIMIT 8")
    return jsonify(total=total, active=active, expired=expired, today=today, new_month=new_month, renew_month=renew_month,
                   revenue=float(revenue), expiring=expiring, recent=recent, registrations=registrations, payments=payments)


@app.get('/api/members')
@role_required('Administrator', 'Manager', 'Receptionist')
def members():
    refresh_expired()
    q = request.args.get('q', '').strip()
    like = f'%{q}%'
    rows = query(
        '''SELECT m.*, ms.start_date,ms.expiry_date,p.name package_name,p.price
           FROM mfa_members m
           LEFT JOIN mfa_memberships ms ON ms.id=(SELECT id FROM mfa_memberships WHERE member_id=m.id ORDER BY expiry_date DESC,id DESC LIMIT 1)
           LEFT JOIN mfa_packages p ON p.id=ms.package_id
           WHERE (%s='' OR m.full_name LIKE %s OR m.member_id LIKE %s OR m.phone LIKE %s OR m.email LIKE %s OR m.qr_code LIKE %s)
             AND (m.status <> 'inactive' OR %s <> '')
           ORDER BY CASE WHEN m.member_id REGEXP '^[0-9]+$' THEN 0 ELSE 1 END, CASE WHEN m.member_id REGEXP '^[0-9]+$' THEN CAST(m.member_id AS UNSIGNED) ELSE 999999999 END, m.created_at DESC''',
        (q, like, like, like, like, like, q)
    )
    return jsonify(rows=rows)


@app.post('/api/members')
@role_required('Administrator', 'Manager', 'Receptionist')
def add_member():
    d = request.json or {}
    required = ['full_name', 'phone', 'email', 'package_id', 'amount']
    if any(not str(d.get(k, '')).strip() for k in required):
        return jsonify(error='Full name, phone, email, package and amount are required.'), 400
    if '@' not in d['email']:
        return jsonify(error='Please enter a valid email address.'), 400
    p = query('SELECT * FROM mfa_packages WHERE id=%s AND active=1', (d['package_id'],), one=True)
    if not p:
        return jsonify(error='Invalid package'), 400

    start = datetime.strptime(d.get('start_date', str(date.today())), '%Y-%m-%d').date()
    expiry = start + timedelta(days=p['duration_days'] - 1)
    qr = 'GM-' + re.sub(r'[^A-Z0-9]', '', __import__('secrets').token_hex(5).upper())
    con = db(); cur = con.cursor()
    try:
        mid = generate_serial_member_id(cur, d.get('manual_member_id'))
        cur.execute(
            '''INSERT INTO mfa_members(member_id,qr_code,full_name,phone,email,gender,emergency_contact,registration_date,status)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (mid, qr, d['full_name'].strip(), d['phone'].strip(), d['email'].strip(), d.get('gender'), d.get('emergency_contact'), date.today(), 'active')
        )
        member_pk = cur.lastrowid
        cur.execute(
            '''INSERT INTO mfa_payments(member_id,package_id,amount,payment_date,payment_method,payment_type,recorded_by)
               VALUES(%s,%s,%s,NOW(),%s,%s,%s)''',
            (member_pk, p['id'], d['amount'], d.get('payment_method', 'Cash'), 'New Registration', session['staff_id'])
        )
        payment_id = cur.lastrowid
        cur.execute(
            '''INSERT INTO mfa_memberships(member_id,package_id,start_date,expiry_date,amount,payment_id)
               VALUES(%s,%s,%s,%s,%s,%s)''',
            (member_pk, p['id'], start, expiry, d['amount'], payment_id)
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        cur.close(); con.close()

    log('Member registered', mid)
    email_sent = False
    email_error = ''
    subject = 'Welcome to Metal Fitness Arena — Your Membership QR Code'
    body = (
        f"Dear {d['full_name']},\n\nWelcome to Metal Fitness Arena. Your membership has been registered successfully.\n\n"
        f"Member ID: {mid}\nPackage: {p['name']}\nMembership start: {start.strftime('%d %B %Y')}\n"
        f"Membership expiry: {expiry.strftime('%d %B %Y')}\n\nYour QR code is attached to this email. Please keep it on your phone and present it at reception for access.\n\n"
        "Thank you for choosing Metal Fitness Arena.\nMFA Management"
    )
    try:
        send_mail(d['email'].strip(), subject, body, qr_bytes(qr), f'MFA-{mid}-QR.png')
        email_sent = True
        email_log(member_pk, d['email'].strip(), subject, 'QR Code', 'sent')
    except Exception as e:
        email_error = str(e)
        email_log(member_pk, d['email'].strip(), subject, 'QR Code', 'failed', email_error)

    return jsonify(member_id=mid, qr_code=qr, expiry=str(expiry), email_sent=email_sent, email_error=email_error), 201


@app.get('/api/members/<member_id>')
@role_required('Administrator', 'Manager', 'Receptionist')
def member(member_id):
    refresh_expired()
    m = query('SELECT * FROM mfa_members WHERE member_id=%s', (member_id,), one=True)
    if not m:
        return jsonify(error='Member not found'), 404
    ms = current_membership(m['id'])
    attendance = query('SELECT checkin_at,status FROM mfa_attendance WHERE member_id=%s ORDER BY checkin_at DESC LIMIT 100', (m['id'],))
    payments = query('''SELECT p.*,pk.name package_name FROM mfa_payments p JOIN mfa_packages pk ON pk.id=p.package_id WHERE p.member_id=%s ORDER BY p.payment_date DESC''', (m['id'],))
    return jsonify(member=m, membership=ms, attendance=attendance, payments=payments)


@app.put('/api/members/<member_id>')
@role_required('Administrator', 'Manager')
def edit_member(member_id):
    d = request.json or {}
    if not d.get('full_name') or not d.get('phone') or not d.get('email'):
        return jsonify(error='Full name, phone and email are required.'), 400
    if '@' not in d['email']:
        return jsonify(error='Please enter a valid email address.'), 400
    exists = query('SELECT id FROM mfa_members WHERE member_id=%s', (member_id,), one=True)
    if not exists:
        return jsonify(error='Member not found'), 404
    query('''UPDATE mfa_members SET full_name=%s,phone=%s,email=%s,gender=%s,emergency_contact=%s WHERE member_id=%s''',
          (d['full_name'].strip(), d['phone'].strip(), d['email'].strip(), d.get('gender'), d.get('emergency_contact'), member_id), commit=True)
    log('Member details updated', member_id)
    return jsonify(ok=True)


@app.post('/api/members/<member_id>/renew')
@role_required('Administrator', 'Manager')
def renew(member_id):
    d = request.json or {}
    m = query('SELECT * FROM mfa_members WHERE member_id=%s', (member_id,), one=True)
    p = query('SELECT * FROM mfa_packages WHERE id=%s AND active=1', (d.get('package_id'),), one=True)
    if not m or not p:
        return jsonify(error='Member or package not found'), 404
    latest = current_membership(m['id'])
    requested_start = datetime.strptime(d.get('start_date', str(date.today())), '%Y-%m-%d').date()
    start = max(requested_start, latest['expiry_date'] + timedelta(days=1) if latest and latest['expiry_date'] >= requested_start else requested_start)
    expiry = start + timedelta(days=p['duration_days'] - 1)
    amount = d.get('amount', p['price'])
    con = db(); cur = con.cursor()
    try:
        cur.execute('''INSERT INTO mfa_payments(member_id,package_id,amount,payment_date,payment_method,payment_type,recorded_by)
                       VALUES(%s,%s,%s,NOW(),%s,%s,%s)''',
                    (m['id'], p['id'], amount, d.get('payment_method', 'Cash'), 'Membership Renewal', session['staff_id']))
        pid = cur.lastrowid
        cur.execute('''INSERT INTO mfa_memberships(member_id,package_id,start_date,expiry_date,amount,payment_id)
                       VALUES(%s,%s,%s,%s,%s,%s)''', (m['id'], p['id'], start, expiry, amount, pid))
        cur.execute("UPDATE mfa_members SET status='active' WHERE id=%s", (m['id'],))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        cur.close(); con.close()
    log('Membership renewed', f'{member_id}: {p["name"]}')
    return jsonify(expiry=str(expiry), start_date=str(start))


@app.post('/api/members/<member_id>/status')
@role_required('Administrator', 'Manager')
def status(member_id):
    st = (request.json or {}).get('status')
    if st not in ('active', 'suspended', 'inactive'):
        return jsonify(error='Invalid status'), 400
    query('UPDATE mfa_members SET status=%s WHERE member_id=%s', (st, member_id), commit=True)
    log('Member status changed', f'{member_id}: {st}')
    return jsonify(ok=True)


@app.post('/api/members/<member_id>/delete')
@role_required('Administrator')
def delete_member(member_id):
    # Archive rather than hard-delete, preserving attendance and payment history.
    m = query('SELECT id,full_name FROM mfa_members WHERE member_id=%s', (member_id,), one=True)
    if not m:
        return jsonify(error='Member not found.'), 404
    query("UPDATE mfa_members SET status='inactive' WHERE member_id=%s", (member_id,), commit=True)
    log('Member archived', f'{member_id}: {m["full_name"]}')
    return jsonify(ok=True, message='Member archived. Attendance and payment history have been preserved.')


@app.get('/api/checkin')
@role_required('Administrator', 'Manager', 'Receptionist')
def checkin_get():
    return jsonify(ok=True)


@app.post('/api/checkin')
@role_required('Administrator', 'Manager', 'Receptionist')
def checkin():
    refresh_expired()
    code = (request.json or {}).get('code', '').strip()
    m = query('SELECT * FROM mfa_members WHERE member_id=%s OR qr_code=%s', (code, code), one=True)
    if not m:
        return jsonify(granted=False, reason='Member not found'), 404
    ms = current_membership(m['id'])
    if m['status'] == 'suspended':
        return jsonify(granted=False, reason='Account suspended', member=m)
    if m['status'] == 'inactive':
        return jsonify(granted=False, reason='Account inactive', member=m)
    if not ms or ms['expiry_date'] < date.today():
        query("UPDATE mfa_members SET status='expired' WHERE id=%s AND status='active'", (m['id'],), commit=True)
        return jsonify(granted=False, reason='Membership expired', member=m, membership=ms)
    exists = query('SELECT id FROM mfa_attendance WHERE member_id=%s AND DATE(checkin_at)=CURDATE()', (m['id'],), one=True)
    if not exists:
        query('INSERT INTO mfa_attendance(member_id,checkin_at,status,staff_id) VALUES(%s,NOW(),%s,%s)', (m['id'], 'active', session['staff_id']), commit=True)
    log('Member check-in', m['member_id'])
    return jsonify(granted=True, member=m, membership=ms, duplicate=bool(exists), checkin_time=datetime.now().strftime('%H:%M:%S'))


@app.get('/api/payments')
@role_required('Administrator', 'Manager')
def payments():
    return jsonify(rows=query('''SELECT p.*,m.member_id,m.full_name,pk.name package_name,s.full_name staff_name
                                 FROM mfa_payments p JOIN mfa_members m ON m.id=p.member_id JOIN mfa_packages pk ON pk.id=p.package_id
                                 LEFT JOIN mfa_staff s ON s.id=p.recorded_by ORDER BY p.payment_date DESC LIMIT 500'''))


@app.get('/api/packages')
@role_required('Administrator', 'Manager', 'Receptionist')
def packages():
    return jsonify(rows=query('SELECT * FROM mfa_packages ORDER BY active DESC,duration_days'))


@app.post('/api/packages')
@role_required('Administrator', 'Manager')
def add_package():
    d = request.json or {}
    if not d.get('name') or not d.get('price') or not d.get('duration_days'):
        return jsonify(error='Package name, price and duration are required.'), 400
    try:
        pid = query('INSERT INTO mfa_packages(name,price,duration_days,description,active) VALUES(%s,%s,%s,%s,%s)',
                    (d['name'].strip(), d['price'], int(d['duration_days']), d.get('description', ''), 1), commit=True)
    except mysql.connector.Error as e:
        return jsonify(error='Package name already exists.' if e.errno == 1062 else str(e)), 400
    log('Package created', d['name'])
    return jsonify(id=pid), 201


@app.put('/api/packages/<int:package_id>')
@role_required('Administrator', 'Manager')
def edit_package(package_id):
    d = request.json or {}
    query('UPDATE mfa_packages SET name=%s,price=%s,duration_days=%s,description=%s,active=%s WHERE id=%s',
          (d['name'].strip(), d['price'], int(d['duration_days']), d.get('description', ''), int(bool(d.get('active', True))), package_id), commit=True)
    log('Package updated', str(package_id))
    return jsonify(ok=True)


@app.get('/api/staff')
@role_required('Administrator')
def staff():
    return jsonify(rows=query('SELECT id,full_name,username,email,role,status,created_at FROM mfa_staff ORDER BY created_at DESC'))


@app.post('/api/staff')
@role_required('Administrator')
def add_staff():
    d = request.json or {}
    required = ['full_name', 'username', 'password', 'role']
    if any(not d.get(k) for k in required):
        return jsonify(error='Full name, username, password and role are required.'), 400
    try:
        query('INSERT INTO mfa_staff(full_name,username,email,password_hash,role,status) VALUES(%s,%s,%s,%s,%s,%s)',
              (d['full_name'], d['username'], d.get('email'), generate_password_hash(d['password']), d['role'], d.get('status', 'active')), commit=True)
    except mysql.connector.Error as e:
        return jsonify(error='Username already exists.' if e.errno == 1062 else str(e)), 400
    log('Staff account created', d['username'])
    return jsonify(ok=True), 201


@app.post('/api/staff/<int:staff_id>/delete')
@role_required('Administrator')
def delete_staff(staff_id):
    if staff_id == session.get('staff_id'):
        return jsonify(error='You cannot remove the staff account you are currently using.'), 400
    staff_row = query('SELECT id,full_name,username FROM mfa_staff WHERE id=%s', (staff_id,), one=True)
    if not staff_row:
        return jsonify(error='Staff account not found.'), 404
    # Disable rather than hard-delete so audit history and payment records remain intact.
    query("UPDATE mfa_staff SET status='disabled' WHERE id=%s", (staff_id,), commit=True)
    log('Staff account removed', f'{staff_row["username"]} ({staff_row["full_name"]}) disabled')
    return jsonify(ok=True, message='Staff account disabled; historical records have been preserved.')


@app.get('/api/activity')
@role_required('Administrator', 'Manager')
def activity():
    return jsonify(rows=query('''SELECT a.*,s.full_name staff_name FROM mfa_activity_log a LEFT JOIN mfa_staff s ON s.id=a.staff_id
                                 ORDER BY a.created_at DESC LIMIT 500'''))


@app.get('/api/email/config')
@role_required('Administrator', 'Manager')
def email_config():
    return jsonify(configured=smtp_configured(), from_email=SMTP['from_email'], from_name=SMTP['from_name'], host=SMTP['host'], port=SMTP['port'])


@app.get('/api/email/recipients')
@role_required('Administrator', 'Manager')
def email_recipients():
    refresh_expired()
    flt = request.args.get('filter', 'all')
    where = ''
    if flt == 'active':
        where = "AND m.status='active'"
    elif flt == 'expired':
        where = "AND m.status='expired'"
    elif flt == 'expiring':
        where = "AND ms.expiry_date BETWEEN CURDATE() AND DATE_ADD(CURDATE(),INTERVAL 7 DAY)"
    rows = query(f'''SELECT m.id,m.member_id,m.full_name,m.email,m.phone,m.status,ms.expiry_date
                     FROM mfa_members m
                     LEFT JOIN mfa_memberships ms ON ms.id=(SELECT id FROM mfa_memberships WHERE member_id=m.id ORDER BY expiry_date DESC,id DESC LIMIT 1)
                     WHERE m.phone IS NOT NULL AND m.phone<>'' {where}
                     ORDER BY m.full_name''')
    return jsonify(rows=rows)


@app.get('/api/email/log')
@role_required('Administrator', 'Manager')
def email_log_list():
    return jsonify(rows=query('''SELECT e.*,m.member_id,m.full_name,s.full_name staff_name
                                 FROM mfa_email_log e LEFT JOIN mfa_members m ON m.id=e.member_id
                                 LEFT JOIN mfa_staff s ON s.id=e.sent_by ORDER BY e.sent_at DESC LIMIT 300'''))


@app.post('/api/email/send')
@role_required('Administrator', 'Manager')
def send_bulk_email():
    d = request.json or {}
    subject = str(d.get('subject', '')).strip()
    body = str(d.get('body', '')).strip()
    member_ids = d.get('member_ids') or []
    if not isinstance(member_ids, list):
        member_ids = []
    member_ids = list(dict.fromkeys(int(x) for x in member_ids if str(x).isdigit()))
    email_type = d.get('email_type', 'Notice')
    if not subject or not body or not member_ids:
        return jsonify(error='Select at least one member and provide a subject and message.'), 400
    if not smtp_configured():
        return jsonify(error='Email is not configured. Set the SMTP settings in .env first.'), 400

    placeholders = ','.join(['%s'] * len(member_ids))
    rows = query(f'''SELECT m.id,m.member_id,m.full_name,m.email,ms.expiry_date
                     FROM mfa_members m
                     LEFT JOIN mfa_memberships ms ON ms.id=(SELECT id FROM mfa_memberships WHERE member_id=m.id ORDER BY expiry_date DESC,id DESC LIMIT 1)
                     WHERE m.id IN ({placeholders}) AND m.email IS NOT NULL AND m.email<>''', tuple(member_ids))
    sent = failed = 0
    results = []
    for m in rows:
        personalized = body.replace('{name}', m['full_name']).replace('{member_id}', m['member_id']).replace('{expiry_date}', str(m['expiry_date'] or ''))
        try:
            send_mail(m['email'], subject.replace('{name}', m['full_name']), personalized)
            email_log(m['id'], m['email'], subject.replace('{name}', m['full_name']), email_type, 'sent')
            sent += 1; results.append({'member_id': m['member_id'], 'email': m['email'], 'status': 'sent'})
        except Exception as e:
            email_log(m['id'], m['email'], subject, email_type, 'failed', str(e))
            failed += 1; results.append({'member_id': m['member_id'], 'email': m['email'], 'status': 'failed', 'error': str(e)})

    log('Bulk email sent', f'{email_type}: {sent} sent, {failed} failed')
    return jsonify(sent=sent, failed=failed, total=len(rows), results=results)


@app.get('/api/messages/config')
@role_required('Administrator', 'Manager')
def messages_config():
    return jsonify(sms_configured=bool(TERMII['api_key'] and TERMII['sender_id']), whatsapp_configured=bool(WHATSAPP['token'] and WHATSAPP['phone_number_id']), whatsapp_template=bool(WHATSAPP['template_name']))


@app.get('/api/messages/log')
@role_required('Administrator', 'Manager')
def messages_log_list():
    return jsonify(rows=query("SELECT l.*,m.member_id,m.full_name FROM mfa_message_log l LEFT JOIN mfa_members m ON m.id=l.member_id ORDER BY l.sent_at DESC LIMIT 300"))


@app.post('/api/messages/send')
@role_required('Administrator', 'Manager')
def send_bulk_message():
    d = request.json or {}
    channel = str(d.get('channel', '')).lower()
    body = str(d.get('body', '')).strip()
    member_ids = d.get('member_ids') or []
    if channel not in ('sms', 'whatsapp'):
        return jsonify(error='Choose SMS or WhatsApp.'), 400
    if not isinstance(member_ids, list):
        member_ids = []
    member_ids = list(dict.fromkeys(int(x) for x in member_ids if str(x).isdigit()))
    if not body or not member_ids:
        return jsonify(error='Select at least one member and enter a message.'), 400
    if channel == 'sms' and not (TERMII['api_key'] and TERMII['sender_id']):
        return jsonify(error='SMS is not configured. Add MFA_TERMII_API_KEY and MFA_TERMII_SENDER_ID to .env.'), 400
    if channel == 'whatsapp' and not (WHATSAPP['token'] and WHATSAPP['phone_number_id']):
        return jsonify(error='WhatsApp is not configured. Add MFA_WHATSAPP_ACCESS_TOKEN and MFA_WHATSAPP_PHONE_NUMBER_ID to .env.'), 400
    placeholders = ','.join(['%s'] * len(member_ids))
    sql = f"SELECT m.id,m.member_id,m.full_name,m.phone,ms.expiry_date FROM mfa_members m LEFT JOIN mfa_memberships ms ON ms.id=(SELECT id FROM mfa_memberships WHERE member_id=m.id ORDER BY expiry_date DESC,id DESC LIMIT 1) WHERE m.id IN ({placeholders}) AND m.phone IS NOT NULL AND m.phone<>''"
    rows = query(sql, tuple(member_ids))
    sent = failed = 0
    results = []
    for m in rows:
        personalized = body.replace('{name}', m['full_name']).replace('{member_id}', m['member_id']).replace('{expiry_date}', str(m['expiry_date'] or ''))
        try:
            provider_id = send_sms(m['phone'], personalized) if channel == 'sms' else send_whatsapp(m['phone'], personalized)
            message_log(m['id'], channel, phone_to_international(m['phone']), personalized, 'sent', provider_id=provider_id)
            sent += 1
            results.append({'member_id': m['member_id'], 'phone': m['phone'], 'status': 'sent', 'provider_id': provider_id})
        except Exception as e:
            try:
                message_log(m['id'], channel, str(m['phone']), personalized, 'failed', str(e))
            except Exception:
                pass
            failed += 1
            results.append({'member_id': m['member_id'], 'phone': m['phone'], 'status': 'failed', 'error': str(e)})
    log(f'Bulk {channel.upper()} sent', f'{sent} accepted, {failed} failed')
    return jsonify(sent=sent, failed=failed, total=len(rows), results=results)


@app.post('/api/members/<member_id>/send-qr')
@role_required('Administrator', 'Manager', 'Receptionist')
def send_member_qr(member_id):
    m = query('SELECT * FROM mfa_members WHERE member_id=%s', (member_id,), one=True)
    if not m:
        return jsonify(error='Member not found'), 404
    if not m['email'] or '@' not in m['email']:
        return jsonify(error='Member does not have a valid email address.'), 400
    subject = 'Your Metal Fitness Arena QR Code'
    body = (f"Dear {m['full_name']},\n\nAttached is your Metal Fitness Arena QR code. "
            f"Your Member ID is {m['member_id']}. Please keep the QR code on your phone and present it at reception.\n\n"
            "Thank you,\nMetal Fitness Arena")
    try:
        send_mail(m['email'], subject, body, qr_bytes(m['qr_code']), f'MFA-{m["member_id"]}-QR.png')
        email_log(m['id'], m['email'], subject, 'QR Code', 'sent')
    except Exception as e:
        email_log(m['id'], m['email'], subject, 'QR Code', 'failed', str(e))
        return jsonify(error=str(e)), 400
    log('QR code emailed', member_id)
    return jsonify(ok=True)


@app.post('/api/change-password')
@role_required('Administrator', 'Manager', 'Receptionist')
def change_password():
    d = request.json or {}
    if not d.get('current_password') or not d.get('new_password') or len(d['new_password']) < 8:
        return jsonify(error='Current password and a new password of at least 8 characters are required.'), 400
    u = query('SELECT password_hash FROM mfa_staff WHERE id=%s', (session['staff_id'],), one=True)
    if not u or not check_password_hash(u['password_hash'], d['current_password']):
        return jsonify(error='Current password is incorrect.'), 400
    query('UPDATE mfa_staff SET password_hash=%s WHERE id=%s', (generate_password_hash(d['new_password']), session['staff_id']), commit=True)
    log('Password changed')
    return jsonify(ok=True)


@app.get('/api/report.csv')
@role_required('Administrator', 'Manager')
def report_csv():
    rows = query('''SELECT m.full_name,m.member_id,m.phone,m.email,m.status,p.name package_name,ms.expiry_date,
                           COUNT(a.id) attendance_count
                    FROM mfa_members m
                    LEFT JOIN mfa_memberships ms ON ms.id=(SELECT id FROM mfa_memberships WHERE member_id=m.id ORDER BY expiry_date DESC,id DESC LIMIT 1)
                    LEFT JOIN mfa_packages p ON p.id=ms.package_id
                    LEFT JOIN mfa_attendance a ON a.member_id=m.id
                    GROUP BY m.id,ms.id,p.id''')
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=['full_name','member_id','phone','email','status','package_name','expiry_date','attendance_count'])
    w.writeheader(); w.writerows(rows); out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='MFA_member_report.csv')


@app.get('/api/qr/<member_id>')
@role_required('Administrator', 'Manager', 'Receptionist')
def qr(member_id):
    m = query('SELECT qr_code FROM mfa_members WHERE member_id=%s', (member_id,), one=True)
    if not m:
        return jsonify(error='Not found'), 404
    return send_file(io.BytesIO(qr_bytes(m['qr_code'])), mimetype='image/png')


with app.app_context():
    try:
        init_db()
    except Exception as e:
        print('Database initialization skipped:', e)


if __name__ == '__main__':
    app.run(host=os.getenv('MFA_HOST', '127.0.0.1'), port=int(os.getenv('MFA_PORT', '5000')), debug=os.getenv('MFA_DEBUG', '0') == '1')
