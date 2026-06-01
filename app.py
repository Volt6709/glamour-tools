import os
from flask import Flask, redirect, request, render_template, url_for, flash
from dotenv import load_dotenv
import qb_auth
import qb_api

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')


@app.route('/')
def index():
    if not qb_auth.is_connected():
        return render_template('connect.html')

    try:
        invoices = qb_api.get_unpaid_invoices()
        estimates = qb_api.get_estimates()
    except Exception as e:
        flash(f'QuickBooks error: {e}', 'error')
        invoices, estimates = [], []

    return render_template('dashboard.html', invoices=invoices, estimates=estimates)


@app.route('/connect')
def connect():
    return redirect(qb_auth.get_auth_url())


@app.route('/callback')
def callback():
    code = request.args.get('code')
    realm_id = request.args.get('realmId')
    error = request.args.get('error')

    if error or not code:
        flash('QuickBooks authorization failed. Please try again.', 'error')
        return redirect(url_for('index'))

    try:
        tokens = qb_auth.exchange_code(code)
        qb_auth.save_tokens(tokens, realm_id)
        flash('Connected to QuickBooks successfully!', 'success')
    except Exception as e:
        flash(f'Connection failed: {e}', 'error')

    return redirect(url_for('index'))


@app.route('/new-estimate', methods=['GET', 'POST'])
def new_estimate():
    if not qb_auth.is_connected():
        return redirect(url_for('connect'))

    if request.method == 'POST':
        client_name = request.form.get('client_name', '').strip()
        client_email = request.form.get('client_email', '').strip()
        message = request.form.get('message', '').strip()

        descriptions = request.form.getlist('description[]')
        amounts = request.form.getlist('amount[]')

        line_items = [
            {'description': d.strip(), 'amount': a}
            for d, a in zip(descriptions, amounts)
            if d.strip() and a
        ]

        if not client_name or not line_items:
            flash('Client name and at least one line item are required.', 'error')
            return render_template('new_estimate.html')

        try:
            estimate = qb_api.create_estimate(client_name, client_email, line_items, message)
            flash(f'Estimate #{estimate.get("DocNumber", "")} created for {client_name}.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Error creating estimate: {e}', 'error')

    return render_template('new_estimate.html')


@app.route('/convert/<estimate_id>')
def convert_estimate(estimate_id):
    if not qb_auth.is_connected():
        return redirect(url_for('connect'))

    try:
        invoice = qb_api.estimate_to_invoice(estimate_id)
        invoice_id = invoice['Id']
        flash(f'Invoice #{invoice.get("DocNumber", "")} created.', 'success')
        return redirect(url_for('send_invoice_page', invoice_id=invoice_id))
    except Exception as e:
        flash(f'Error converting estimate: {e}', 'error')
        return redirect(url_for('index'))


@app.route('/send/<invoice_id>', methods=['GET', 'POST'])
def send_invoice_page(invoice_id):
    if not qb_auth.is_connected():
        return redirect(url_for('connect'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Email address is required.', 'error')
        else:
            try:
                qb_api.send_invoice(invoice_id, email)
                flash(f'Invoice sent to {email}.', 'success')
                return redirect(url_for('index'))
            except Exception as e:
                flash(f'Error sending invoice: {e}', 'error')

    try:
        invoice = qb_api.get_invoice(invoice_id)
    except Exception:
        invoice = {}

    prefill_email = invoice.get('BillEmail', {}).get('Address', '')
    return render_template('send_invoice.html', invoice_id=invoice_id, invoice=invoice, prefill_email=prefill_email)


if __name__ == '__main__':
    print('\n  Glamour Tools is running.')
    print('  Open http://localhost:5000 in your browser.\n')
    app.run(debug=False, port=5000)
