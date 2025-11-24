# app.py (full — copy & replace your existing file)
import os
import hashlib
import random
from datetime import datetime, timedelta
import pathlib
import json

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'foodshare.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

####################
# Auto-create minimal templates + css (dev helper)
# This prevents TemplateNotFound while you test. It will NOT overwrite files if they exist.
####################
def ensure_templates_files():
    base = pathlib.Path(__file__).parent.resolve()
    tpl_dir = base / "templates"
    css_dir = base / "static" / "css"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    css_dir.mkdir(parents=True, exist_ok=True)

    templates = {
        "index.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>FoodShare</title>
<link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}">
</head><body>
<h1>FoodShare Home</h1>
<p><a href="{{ url_for('register') }}">Register</a> | <a href="{{ url_for('login') }}">Login</a></p>
</body></html>
""",
        "register.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Register</title></head><body>
<h1>Register</h1>
<form method="post" action="{{ url_for('register') }}">
  <label>Name</label><br><input name="name"><br>
  <label>Phone (with country code)</label><br><input name="phone" required><br>
  <label>Role</label><br>
  <select name="role"><option value="donor">Donor</option><option value="receiver">Receiver</option><option value="delivery">Delivery</option></select><br>
  <button type="submit">Register</button>
</form>
</body></html>
""",
        "login.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Login</title></head><body>
<h1>Login</h1>
<form method="post" action="{{ url_for('login') }}">
  <label>Phone</label><br><input name="phone" required><br>
  <button type="submit">Send OTP</button>
</form>
</body></html>
""",
        "confirm_otp.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Confirm OTP</title></head><body>
<h1>Confirm OTP for {{ phone }}</h1>
{% if dev_otp %}<div style="background:#fffae6;padding:8px;margin-bottom:8px;">DEV OTP: <strong>{{ dev_otp }}</strong></div>{% endif %}
<form method="post">
  <label>OTP</label><br><input name="otp" required><br>
  <button type="submit">Confirm</button>
</form>
</body></html>
""",
        "donor_dashboard.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Donor Dashboard</title>
<link rel="stylesheet" href="{{ url_for('static', filename='css/styles.css') }}"></head><body>
<h1>Donor Dashboard</h1>
<p>Welcome, {{ current_user.name or current_user.phone }}</p>

<h2>Create Listing (Post Food)</h2>
<form method="post" action="{{ url_for('donor_create') }}">
  <label>Title</label><br><input name="title" required><br>
  <label>Description</label><br><textarea name="description"></textarea><br>
  <label>Servings</label><br><input type="number" name="servings" value="1" min="1"><br>
  <label>Pickup time</label><br><input name="pickup_time" placeholder="ASAP or e.g. 2:00 PM"><br>
  <button type="submit">Post</button>
</form>

<h2>Your Listings</h2>
{% if listings %}
  <ul>
  {% for li in listings %}
    <li><strong>{{ li.title }}</strong> — {{ li.servings }} servings — {{ li.status }}
      <div>{{ li.description }}</div>
      <div>Pickup: {{ li.pickup_time }}</div>
    </li>
  {% endfor %}
  </ul>
{% else %}
  <p>No listings yet.</p>
{% endif %}
<p><a href="{{ url_for('logout') }}">Logout</a></p>
</body></html>
""",
        "donor_create.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Create Listing</title></head><body>
<h1>Create Listing (Donor)</h1>
<form method="post" action="{{ url_for('donor_create') }}">
  <label>Title</label><br><input name="title" required><br>
  <label>Description</label><br><textarea name="description"></textarea><br>
  <label>Servings</label><br><input type="number" name="servings" value="1"><br>
  <label>Pickup time</label><br><input name="pickup_time"><br>
  <button type="submit">Create</button>
</form>
</body></html>
""",
        "listings.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Available Listings</title></head><body>
<h1>Available Listings</h1>
{% if listings %}
  <ul>
  {% for li in listings %}
    <li><strong>{{ li.title }}</strong> — {{ li.servings }} servings
      <p>{{ li.description }}</p>
      <form method="post" action="{{ url_for('request_listing', listing_id=li.id) }}">
        <button type="submit">Request</button>
      </form>
    </li>
  {% endfor %}
  </ul>
{% else %}
  <p>No available listings.</p>
{% endif %}
<p><a href="{{ url_for('logout') }}">Logout</a></p>
</body></html>
""",
        "delivery_dashboard.html": """<!doctype html>
<html><head><meta charset="utf-8"><title>Delivery Dashboard</title></head><body>
<h1>Delivery Dashboard</h1>
{% if jobs %}
  <ul>
  {% for job in jobs %}
    <li>Job #{{ job.id }} — Listing: {{ job.listing_id }} — Status: {{ job.status }}
      <form method="post" action="{{ url_for('assign_job', job_id=job.id) }}">
        <button type="submit">Accept</button>
      </form>
    </li>
  {% endfor %}
  </ul>
{% else %}
  <p>No jobs right now.</p>
{% endif %}
<p><a href="{{ url_for('logout') }}">Logout</a></p>
</body></html>
"""
    }

    css_content = "body { font-family: Arial, sans-serif; background:#f7f7f7; padding:20px; } h1{color:#333;}"

    for name, content in templates.items():
        p = tpl_dir / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            print("Created template:", p)

    css_file = css_dir / "styles.css"
    if not css_file.exists():
        css_file.write_text(css_content, encoding="utf-8")
        print("Created css:", css_file)

# create templates/css if missing
ensure_templates_files()

####################
# Models
####################
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120))
    role = db.Column(db.String(20))  # donor | receiver | delivery
    password_hash = db.Column(db.String(128))  # optional if using OTP-only
    verified = db.Column(db.Boolean, default=False)

class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    servings = db.Column(db.Integer)
    pickup_time = db.Column(db.String(100))
    pickup_lat = db.Column(db.Float, nullable=True)
    pickup_lng = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(30), default='available')  # available, reserved, picked, delivered

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    listing_id = db.Column(db.Integer, db.ForeignKey('listing.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    delivery_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(30), default='requested')  # requested, assigned, enroute, picked, delivered
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    picked_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)
    code_hash = db.Column(db.String(128), nullable=False)
    purpose = db.Column(db.String(30))  # signup | pickup | delivery_confirm
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

####################
# Helpers
####################
def hash_code(code: str, salt: str = '') -> str:
    return hashlib.sha256((code + salt).encode()).hexdigest()

def gen_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"

def send_otp(phone: str, code: str, purpose: str):
    # DEV: print OTP to console. Replace with SMS provider in prod.
    print(f"[DEV SMS] OTP for {phone} ({purpose}) = {code}")

def create_and_send_otp(phone: str, purpose: str) -> None:
    code = gen_otp_code()
    otp_hash = hash_code(code)
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    otp = OTP(phone=phone, code_hash=otp_hash, purpose=purpose, expires_at=expires_at)
    db.session.add(otp)
    db.session.commit()
    send_otp(phone, code, purpose)
    session['dev_last_otp'] = code  # dev helper

def verify_otp(phone: str, code: str, purpose: str) -> bool:
    now = datetime.utcnow()
    otp_records = OTP.query.filter_by(phone=phone, purpose=purpose, used=False).order_by(OTP.expires_at.desc()).all()
    for otp in otp_records:
        if otp.expires_at < now:
            continue
        if otp.code_hash == hash_code(code):
            otp.used = True
            db.session.commit()
            return True
    return False

####################
# Auth
####################
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None

def ensure_db_created():
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    db.create_all()

# debug route to show template searchpath (optional)
@app.route('/_what_templates')
def _what_templates():
    search = app.jinja_loader.searchpath if hasattr(app.jinja_loader, 'searchpath') else []
    files = {p: os.listdir(p) if os.path.isdir(p) else [] for p in search}
    return "<pre>" + json.dumps({"searchpath": search, "files": files}, indent=2) + "</pre>"

####################
# Routes
####################
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        name = request.form.get('name','').strip()
        role = request.form['role']
        user = User.query.filter_by(phone=phone).first()
        if user:
            flash('Phone already exists. Please login or verify.', 'warning')
            return redirect(url_for('login'))
        user = User(phone=phone, name=name, role=role, verified=False)
        db.session.add(user)
        db.session.commit()
        create_and_send_otp(phone, 'signup')
        session['pending_phone'] = phone
        flash('OTP sent to your phone (dev console). Enter it to verify.', 'info')
        return redirect(url_for('confirm_otp', purpose='signup'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        phone = request.form['phone'].strip()
        user = User.query.filter_by(phone=phone).first()
        if not user:
            flash('No account for this phone. Please register.', 'warning')
            return redirect(url_for('register'))
        create_and_send_otp(phone, 'login')
        session['pending_phone'] = phone
        return redirect(url_for('confirm_otp', purpose='login'))
    return render_template('login.html')

@app.route('/confirm-otp/<purpose>', methods=['GET','POST'])
def confirm_otp(purpose):
    phone = session.get('pending_phone')
    if not phone:
        flash('No pending phone. Start from login/register.', 'warning')
        return redirect(url_for('index'))
    if request.method == 'POST':
        code = request.form['otp'].strip()
        ok = verify_otp(phone, code, purpose if purpose in ('signup','login') else purpose)
        if not ok:
            flash('Invalid or expired OTP.', 'danger')
            return redirect(url_for('confirm_otp', purpose=purpose))
        user = User.query.filter_by(phone=phone).first()
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('register'))
        user.verified = True
        db.session.commit()
        login_user(user)
        flash('Authentication successful.', 'success')
        return redirect(url_for('dashboard'))
    dev_otp = session.get('dev_last_otp')
    return render_template('confirm_otp.html', phone=phone, purpose=purpose, dev_otp=dev_otp)

@app.route('/dashboard')
@login_required
def dashboard():
    role = (current_user.role or '').lower()
    if role == 'donor':
        listings = Listing.query.filter_by(donor_id=current_user.id).all()
        return render_template('donor_dashboard.html', listings=listings)
    elif role == 'receiver':
        listings = Listing.query.filter_by(status='available').all()
        return render_template('listings.html', listings=listings)
    elif role == 'delivery':
        jobs = Job.query.filter(Job.status.in_(['requested','assigned'])).all()
        return render_template('delivery_dashboard.html', jobs=jobs)
    else:
        flash('Unknown role. Please contact admin.', 'warning')
        return render_template('index.html')

@app.route('/donor/create', methods=['GET','POST'])
@login_required
def donor_create():
    if (current_user.role or '').lower() != 'donor':
        flash('Only donors can create listings.', 'warning')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        desc = request.form.get('description','')
        servings = int(request.form.get('servings',1))
        pickup_time = request.form.get('pickup_time','ASAP')
        listing = Listing(donor_id=current_user.id, title=title, description=desc,
                          servings=servings, pickup_time=pickup_time, status='available')
        db.session.add(listing)
        db.session.commit()
        flash('Listing created.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('donor_create.html')

@app.route('/listing/<int:listing_id>/request', methods=['POST'])
@login_required
def request_listing(listing_id):
    if (current_user.role or '').lower() != 'receiver':
        return jsonify({'error':'Only receivers can request'}), 403
    listing = Listing.query.get_or_404(listing_id)
    if listing.status != 'available':
        return jsonify({'error':'Listing not available'}), 400
    job = Job(listing_id=listing.id, receiver_id=current_user.id, status='requested')
    listing.status = 'reserved'
    db.session.add(job)
    db.session.commit()
    flash('Requested listing. Waiting for delivery assignment.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/job/<int:job_id>/assign', methods=['POST'])
@login_required
def assign_job(job_id):
    if (current_user.role or '').lower() != 'delivery':
        return jsonify({'error':'Only delivery persons can accept jobs'}), 403
    job = Job.query.get_or_404(job_id)
    if job.delivery_id:
        return jsonify({'error':'Already assigned'}), 400
    job.delivery_id = current_user.id
    job.status = 'assigned'
    db.session.commit()
    listing = Listing.query.get(job.listing_id)
    donor = db.session.get(User, listing.donor_id)
    create_and_send_otp(donor.phone, 'pickup')
    flash('Job assigned. Pickup OTP sent to donor (dev console).', 'success')
    return redirect(url_for('dashboard'))

@app.route('/job/<int:job_id>/confirm-pickup', methods=['GET','POST'])
@login_required
def confirm_pickup(job_id):
    job = Job.query.get_or_404(job_id)
    if request.method == 'POST':
        otp = request.form['otp'].strip()
        listing = Listing.query.get(job.listing_id)
        donor = db.session.get(User, listing.donor_id)
        ok = verify_otp(donor.phone, otp, 'pickup')
        if not ok:
            flash('Invalid pickup OTP.', 'danger')
            return redirect(url_for('confirm_pickup', job_id=job_id))
        job.status = 'picked'
        job.picked_at = datetime.utcnow()
        listing.status = 'picked'
        db.session.commit()
        receiver = db.session.get(User, job.receiver_id)
        create_and_send_otp(receiver.phone, 'delivery_confirm')
        flash('Pickup confirmed. Delivery OTP sent to receiver (dev console).', 'success')
        return redirect(url_for('dashboard'))
    return render_template('confirm_otp.html', purpose='pickup')

@app.route('/job/<int:job_id>/confirm-delivery', methods=['GET','POST'])
@login_required
def confirm_delivery(job_id):
    job = Job.query.get_or_404(job_id)
    if request.method == 'POST':
        otp = request.form['otp'].strip()
        receiver = db.session.get(User, job.receiver_id)
        ok = verify_otp(receiver.phone, otp, 'delivery_confirm')
        if not ok:
            flash('Invalid delivery OTP.', 'danger')
            return redirect(url_for('confirm_delivery', job_id=job_id))
        job.status = 'delivered'
        job.delivered_at = datetime.utcnow()
        listing = Listing.query.get(job.listing_id)
        listing.status = 'delivered'
        db.session.commit()
        flash('Delivery confirmed. Job completed.', 'success')
        return redirect(url_for('dashboard'))
    return render_template('confirm_otp.html', purpose='delivery_confirm')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        ensure_db_created()
    app.run(debug=True)
