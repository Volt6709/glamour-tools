import os
import uuid
from flask import Flask, redirect, request, render_template, url_for, flash, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import qb_auth
import qb_api
import db
import email_reader
import outreach
from logger import log_error, log_info

load_dotenv()
db.init_db()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'fabric_photos')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'heic'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(file):
    if not file or file.filename == '':
        return None
    if not allowed_file(file.filename):
        return None
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return filename


# ── Auth ─────────────────────────────────────────────────────────────────────

@app.route('/connect')
def connect():
    return redirect(qb_auth.get_auth_url())


@app.route('/callback')
def callback():
    code = request.args.get('code')
    realm_id = request.args.get('realmId')
    if not code:
        flash('QuickBooks authorization failed.', 'error')
        return redirect(url_for('index'))
    try:
        tokens = qb_auth.exchange_code(code)
        qb_auth.save_tokens(tokens, realm_id)
        flash('Connected to QuickBooks!', 'success')
    except Exception as e:
        flash(f'Connection failed: {e}', 'error')
    return redirect(url_for('index'))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if not qb_auth.is_connected():
        return render_template('connect.html')

    try:
        invoices = qb_api.get_unpaid_invoices()
        estimates = qb_api.get_estimates()
    except Exception as e:
        log_error('dashboard', e)
        flash(f'QuickBooks error: {e}', 'error')
        invoices, estimates = [], []

    stats = db.get_fabric_stats()
    lead_stats = db.get_lead_stats()
    new_emails = sum(1 for e in email_reader.fetch_recent(10) if e.get('is_job') and 'error' not in e)

    return render_template('dashboard.html',
                           invoices=invoices,
                           estimates=estimates,
                           fabric_stats=stats,
                           lead_stats=lead_stats,
                           new_job_emails=new_emails)


# ── Estimates & Invoices ──────────────────────────────────────────────────────

@app.route('/new-estimate', methods=['GET', 'POST'])
def new_estimate():
    if not qb_auth.is_connected():
        return redirect(url_for('connect'))

    # Pre-fill from email if coming from inbox
    prefill = {
        'client_name': request.args.get('client_name', ''),
        'client_email': request.args.get('client_email', ''),
        'message': request.args.get('message', ''),
        'from_email_id': request.args.get('email_id', ''),
    }

    if request.method == 'POST':
        client_name = request.form.get('client_name', '').strip()
        client_email = request.form.get('client_email', '').strip()
        message = request.form.get('message', '').strip()
        from_email_id = request.form.get('from_email_id', '')

        descriptions = request.form.getlist('description[]')
        amounts = request.form.getlist('amount[]')
        line_items = [
            {'description': d.strip(), 'amount': a}
            for d, a in zip(descriptions, amounts)
            if d.strip() and a
        ]

        if not client_name or not line_items:
            flash('Client name and at least one line item are required.', 'error')
            return render_template('new_estimate.html', prefill=prefill)

        try:
            estimate = qb_api.create_estimate(client_name, client_email, line_items, message)
            if from_email_id:
                db.mark_email_used(from_email_id, estimate.get('Id', ''))
            flash(f"Estimate #{estimate.get('DocNumber', '')} created for {client_name}.", 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error creating estimate: {e}', 'error')

    return render_template('new_estimate.html', prefill=prefill)


@app.route('/convert/<estimate_id>')
def convert_estimate(estimate_id):
    if not qb_auth.is_connected():
        return redirect(url_for('connect'))
    try:
        invoice = qb_api.estimate_to_invoice(estimate_id)
        flash(f"Invoice #{invoice.get('DocNumber', '')} created.", 'success')
        return redirect(url_for('send_invoice_page', invoice_id=invoice['Id']))
    except Exception as e:
        flash(f'Error converting estimate: {e}', 'error')
        return redirect(url_for('index'))


@app.route('/send/<invoice_id>', methods=['GET', 'POST'])
def send_invoice_page(invoice_id):
    if not qb_auth.is_connected():
        return redirect(url_for('connect'))

    invoice = {}
    prefill_email = ''
    try:
        invoice = qb_api.get_invoice(invoice_id)
        prefill_email = invoice.get('BillEmail', {}).get('Address', '')
    except Exception:
        pass

    if request.method == 'POST':
        email_addr = request.form.get('email', '').strip()
        if not email_addr:
            flash('Email address is required.', 'error')
        else:
            try:
                qb_api.send_invoice(invoice_id, email_addr)
                flash(f'Invoice sent to {email_addr}.', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                flash(f'Error sending invoice: {e}', 'error')

    return render_template('send_invoice.html', invoice_id=invoice_id, invoice=invoice, prefill_email=prefill_email)


# ── Inbox ─────────────────────────────────────────────────────────────────────

@app.route('/inbox')
def inbox():
    if not email_reader.is_configured():
        flash('Add SMTP_PASSWORD to .env to enable inbox reading.', 'error')
        return redirect(url_for('index'))
    emails = email_reader.fetch_recent(40)
    return render_template('inbox.html', emails=emails)


@app.route('/inbox/<email_id>')
def view_email(email_id):
    msg = email_reader.fetch_one(email_id)
    if not msg:
        flash('Could not load email.', 'error')
        return redirect(url_for('inbox'))
    return render_template('email_detail.html', msg=msg)


# ── Inventory ─────────────────────────────────────────────────────────────────

@app.route('/inventory')
def inventory():
    search = request.args.get('q', '').strip()
    client = request.args.get('client', '').strip()
    fabrics = db.get_fabrics(search=search, client=client)
    clients = db.get_clients()
    return render_template('inventory.html', fabrics=fabrics, clients=clients,
                           search=search, active_client=client)


@app.route('/inventory/add', methods=['GET', 'POST'])
def add_fabric():
    clients = db.get_clients()
    prefill_client = request.args.get('client', '')

    if request.method == 'POST':
        photo_file = request.files.get('photo')
        photo_path = save_photo(photo_file)

        db.add_fabric(
            client_name=request.form.get('client_name', '').strip(),
            fabric_type=request.form.get('fabric_type', '').strip(),
            color=request.form.get('color', '').strip(),
            pattern=request.form.get('pattern', '').strip(),
            yardage=request.form.get('yardage') or None,
            location=request.form.get('location', '').strip(),
            supplier=request.form.get('supplier', '').strip(),
            notes=request.form.get('notes', '').strip(),
            photo_path=photo_path,
        )
        flash('Fabric added to inventory.', 'success')
        next_url = request.form.get('next') or url_for('inventory')
        return redirect(next_url)

    return render_template('add_fabric.html', clients=clients, prefill_client=prefill_client)


@app.route('/inventory/<int:fabric_id>', methods=['GET', 'POST'])
def fabric_detail(fabric_id):
    fabric = db.get_fabric(fabric_id)
    if not fabric:
        flash('Fabric not found.', 'error')
        return redirect(url_for('inventory'))

    clients = db.get_clients()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete':
            db.delete_fabric(fabric_id)
            flash('Fabric removed from inventory.', 'success')
            return redirect(url_for('inventory'))

        photo_file = request.files.get('photo')
        photo_path = save_photo(photo_file)

        db.update_fabric(
            fabric_id=fabric_id,
            client_name=request.form.get('client_name', '').strip(),
            fabric_type=request.form.get('fabric_type', '').strip(),
            color=request.form.get('color', '').strip(),
            pattern=request.form.get('pattern', '').strip(),
            yardage=request.form.get('yardage') or None,
            location=request.form.get('location', '').strip(),
            supplier=request.form.get('supplier', '').strip(),
            notes=request.form.get('notes', '').strip(),
            photo_path=photo_path,
        )
        flash('Fabric updated.', 'success')
        return redirect(url_for('fabric_detail', fabric_id=fabric_id))

    return render_template('fabric_detail.html', fabric=fabric, clients=clients)


# ── Outreach ──────────────────────────────────────────────────────────────────

@app.route('/outreach')
def outreach_list():
    status_filter = request.args.get('status', '')
    leads = db.get_leads(status=status_filter)
    stats = db.get_lead_stats()
    return render_template('outreach.html', leads=leads, stats=stats, status_filter=status_filter)


@app.route('/outreach/add', methods=['GET', 'POST'])
def add_lead():
    if request.method == 'POST':
        db.add_lead(
            name=request.form.get('name', '').strip(),
            firm=request.form.get('firm', '').strip(),
            email=request.form.get('email', '').strip(),
            phone=request.form.get('phone', '').strip(),
            location=request.form.get('location', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )
        flash('Lead added.', 'success')
        return redirect(url_for('outreach_list'))
    return render_template('add_lead.html')


@app.route('/outreach/send/<int:lead_id>')
def send_outreach(lead_id):
    lead = db.get_lead(lead_id)
    if not lead or not lead['email']:
        flash('Lead has no email address.', 'error')
        return redirect(url_for('outreach_list'))
    if not outreach.is_configured():
        flash('Add SMTP_PASSWORD to .env to enable email sending.', 'error')
        return redirect(url_for('outreach_list'))

    status = lead['status']
    try:
        if status == 'new':
            outreach.send_cold_email(lead)
            db.update_lead_status(lead_id, 'emailed', 'emailed_at')
            flash(f"Cold email sent to {lead['name']}.", 'success')
        elif status == 'emailed':
            outreach.send_followup1(lead)
            db.update_lead_status(lead_id, 'followup1', 'followup1_at')
            flash(f"Follow-up 1 sent to {lead['name']}.", 'success')
        elif status == 'followup1':
            outreach.send_followup2(lead)
            db.update_lead_status(lead_id, 'followup2', 'followup2_at')
            flash(f"Final follow-up sent to {lead['name']}.", 'success')
        else:
            flash('No further emails to send for this lead.', 'error')
    except Exception as e:
        flash(f'Email failed: {e}', 'error')

    return redirect(url_for('outreach_list'))


@app.route('/outreach/mark/<int:lead_id>/<status>')
def mark_lead(lead_id, status):
    allowed = {'new', 'emailed', 'followup1', 'followup2', 'responded', 'converted', 'lost'}
    if status in allowed:
        db.update_lead_status(lead_id, status)
        flash(f'Lead marked as {status}.', 'success')
    return redirect(url_for('outreach_list'))


@app.route('/outreach/delete/<int:lead_id>')
def delete_lead(lead_id):
    db.delete_lead(lead_id)
    flash('Lead removed.', 'success')
    return redirect(url_for('outreach_list'))


@app.route('/static/fabric_photos/<filename>')
def fabric_photo(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('\n  Glamour Tools is running.')
    print('  Open http://localhost:5000 in your browser.\n')
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, port=port)
