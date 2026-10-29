import xmlrpc.client
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("ODOO_URL").strip()
db = os.getenv("ODOO_DB").strip()
username = os.getenv("ODOO_USERNAME").strip()
password = os.getenv("ODOO_PASSWORD").strip()

print("URL:", url)
print("DB:", db)
print("Username:", username)

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
print("Server version:", common.version())

uid = common.authenticate(db, username, password, {})
print("UID result:", uid)

if not uid:
    print("❌ Authentication failed - تحقق من username/password/db name")
else:
    print("✅ Authentication succeeded")