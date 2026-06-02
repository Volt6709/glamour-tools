import requests
from qb_auth import get_valid_token, BASE_URL
from logger import log_api_call, log_error

MV = '65'  # minorversion


def _headers():
    token, _ = get_valid_token()
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }


def _checked(resp, method='GET'):
    tid = resp.headers.get('intuit_tid')
    try:
        resp.raise_for_status()
        log_api_call(method, resp.url, resp.status_code, intuit_tid=tid)
    except requests.HTTPError as e:
        log_api_call(method, resp.url, resp.status_code, intuit_tid=tid, error=str(e))
        raise
    return resp


def _realm():
    from qb_auth import load_tokens
    t = load_tokens()
    return t['realm_id'] if t else None


def _url(path):
    return f"{BASE_URL}/{_realm()}/{path}"


def get_or_create_customer(name, email=''):
    query = f"SELECT * FROM Customer WHERE DisplayName = '{name.replace(chr(39), chr(39)*2)}'"
    resp = requests.get(_url('query'), headers=_headers(), params={'query': query, 'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    customers = resp.json().get('QueryResponse', {}).get('Customer', [])
    if customers:
        return customers[0]['Id']

    payload = {'DisplayName': name}
    if email:
        payload['PrimaryEmailAddr'] = {'Address': email}
    resp = requests.post(_url('customer'), json=payload, headers=_headers(), params={'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    return resp.json()['Customer']['Id']


def create_estimate(client_name, client_email, line_items, message=''):
    customer_id = get_or_create_customer(client_name, client_email)

    lines = []
    for item in line_items:
        line = {
            'DetailType': 'SalesItemLineDetail',
            'Amount': round(float(item['amount']), 2),
            'Description': item['description'],
            'SalesItemLineDetail': {
                'UnitPrice': round(float(item['amount']), 2),
                'Qty': int(item.get('qty', 1)),
            },
        }
        lines.append(line)

    payload = {'CustomerRef': {'value': customer_id}, 'Line': lines}
    if message:
        payload['CustomerMemo'] = {'value': message}
    if client_email:
        payload['BillEmail'] = {'Address': client_email}

    resp = requests.post(_url('estimate'), json=payload, headers=_headers(), params={'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    return resp.json()['Estimate']


def get_estimates():
    query = "SELECT * FROM Estimate WHERE TxnStatus IN ('Pending', 'Accepted') ORDERBY MetaData.CreateTime DESC MAXRESULTS 25"
    resp = requests.get(_url('query'), headers=_headers(), params={'query': query, 'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    return resp.json().get('QueryResponse', {}).get('Estimate', [])


def estimate_to_invoice(estimate_id):
    resp = requests.get(_url(f'estimate/{estimate_id}'), headers=_headers(), params={'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    est = resp.json()['Estimate']

    payload = {
        'CustomerRef': est['CustomerRef'],
        'Line': est['Line'],
        'LinkedTxn': [{'TxnId': estimate_id, 'TxnType': 'Estimate'}],
    }
    if est.get('BillEmail'):
        payload['BillEmail'] = est['BillEmail']

    resp = requests.post(_url('invoice'), json=payload, headers=_headers(), params={'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    return resp.json()['Invoice']


def send_invoice(invoice_id, email):
    resp = requests.post(
        _url(f'invoice/{invoice_id}/send'),
        headers=_headers(),
        params={'sendTo': email, 'minorversion': MV},
        timeout=10,
    )
    resp = _checked(resp)
    return resp.json()


def get_unpaid_invoices():
    query = "SELECT * FROM Invoice WHERE Balance > '0' ORDERBY DueDate MAXRESULTS 50"
    resp = requests.get(_url('query'), headers=_headers(), params={'query': query, 'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    return resp.json().get('QueryResponse', {}).get('Invoice', [])


def get_invoice(invoice_id):
    resp = requests.get(_url(f'invoice/{invoice_id}'), headers=_headers(), params={'minorversion': MV}, timeout=10)
    resp = _checked(resp)
    return resp.json()['Invoice']
