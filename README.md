# Receipt Splitter

A small self-hosted web app for shared households. Housemates photograph their shopping receipts, the app reads them with OCR, and at the end of a period it works out each person's fair share and who owes whom.

## Features

- **Receipt scanning:** upload a photo and the store, date, items, discounts and total are extracted automatically, ready to review and correct.
- **Uploader and payer tracking:** each receipt records who uploaded it and who paid for it.
- **Settle expenses:** for any date range, shows the total spent, each member's equal share, what each person paid (and for which receipts), their balance, and a short list of who pays whom.
- **Admin only controls:** managing users and deleting receipts require an admin login.

## Tech stack

| Area | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite |
| OCR | PaddleOCR (default), Tesseract (fallback) |
| Frontend | HTML, CSS, vanilla JavaScript (Jinja templates) |

OCR runs locally, so receipt images never leave the machine.

## Setup (Ubuntu)

PaddlePaddle currently supports Python up to 3.13, so the easiest route is [uv](https://docs.astral.sh/uv/):

```bash
sudo apt install -y git tesseract-ocr tesseract-ocr-eng
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone <repo-url> receipt-splitter
cd receipt-splitter
uv venv --python 3.13 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

The first scan downloads the PaddleOCR models (about 20 MB) and is slower than later scans.

## First run

```bash
python set_admin_password.py          # set the admin password
python add_users.py Alice Bob Carol   # add household members
```

## Running

```bash
flask --app app run --host 0.0.0.0 --port 5000
```

Open `http://<server-ip>:5000` from any device on the same network. If a firewall is enabled, allow the port with `sudo ufw allow 5000/tcp`.

**Keep it on a trusted local network.** Do not expose it to the internet.

## Configuration

| Variable | Purpose |
|---|---|
| `OCR_ENGINE` | `paddle` (default) or `tesseract` |
| `SECRET_KEY` | Optional. Signs the admin login cookie. If unset, one is generated and stored in `.secret_key` |

## Project structure

```
app.py                 Flask routes and API
db.py                  SQLite storage and migrations
ocr.py                 OCR engines and receipt text parsing
settle.py              Share, balance and who-pays-whom calculation
templates/index.html   User interface
add_users.py           Add members from the command line
set_admin_password.py  Set or change the admin password
test_ocr.py            Scan the newest upload and print the result
```
