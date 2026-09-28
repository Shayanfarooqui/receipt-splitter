"""
Settlement — work out who owes whom for a period.

Everyone pays for shopping out of their own pocket. At settle-up time:
  share   = total spent / number of members
  balance = paid - share   (positive: is owed money, negative: owes money)
Then debts are paired off into as few payments as practical.
All maths is done in pence to avoid rounding drift.
"""


def _pence(amount):
    return int(round(float(amount or 0) * 100))


def compute_settlement(receipts, users):
    """
    receipts: dicts with id, store_name, date, total_amount, paid_by
    users:    dicts with id, name
    """
    members = sorted(users, key=lambda u: u['name'].lower())
    member_ids = {u['id'] for u in members}

    counted = [r for r in receipts if r.get('paid_by') in member_ids]
    unassigned = [r for r in receipts if r.get('paid_by') not in member_ids]

    total_p = sum(_pence(r['total_amount']) for r in counted)
    n = len(members)

    # Split the total into shares; any leftover pence go one each to the first members
    base, rem = divmod(total_p, n) if n else (0, 0)

    people = []
    for i, u in enumerate(members):
        paid_receipts = [r for r in counted if r['paid_by'] == u['id']]
        paid_p = sum(_pence(r['total_amount']) for r in paid_receipts)
        share_p = base + (1 if i < rem else 0)
        people.append({
            'id': u['id'],
            'name': u['name'],
            'paid_p': paid_p,
            'share_p': share_p,
            'balance_p': paid_p - share_p,
            'receipts': [{
                'id': r['id'],
                'store_name': r['store_name'],
                'date': r['date'],
                'total_amount': r['total_amount'],
            } for r in paid_receipts],
        })

    # Pair the biggest debtor with the biggest creditor until everyone is square
    creditors = sorted([[p['balance_p'], p['name']] for p in people if p['balance_p'] > 0], reverse=True)
    debtors = sorted([[-p['balance_p'], p['name']] for p in people if p['balance_p'] < 0], reverse=True)
    transfers = []
    ci = di = 0
    while ci < len(creditors) and di < len(debtors):
        amount = min(creditors[ci][0], debtors[di][0])
        transfers.append({'from': debtors[di][1], 'to': creditors[ci][1], 'amount': amount / 100})
        creditors[ci][0] -= amount
        debtors[di][0] -= amount
        if creditors[ci][0] == 0:
            ci += 1
        if debtors[di][0] == 0:
            di += 1

    for p in people:
        p['paid'] = p.pop('paid_p') / 100
        p['share'] = p.pop('share_p') / 100
        p['balance'] = p.pop('balance_p') / 100

    return {
        'total': total_p / 100,
        'members': n,
        'per_person': round(total_p / n / 100, 2) if n else 0,
        'receipt_count': len(counted),
        'people': people,
        'transfers': transfers,
        'unassigned': [{
            'id': r['id'], 'store_name': r['store_name'],
            'date': r['date'], 'total_amount': r['total_amount'],
        } for r in unassigned],
    }
