import os

os.environ.setdefault("PRINTAPP_PIN_HASH", "0" * 64)
os.environ.setdefault("PRINTAPP_SECRET_KEY", "test-secret")
os.environ.setdefault("PRINTAPP_PRINTER", "DCP-L2540DW")

import app

client = app.app.test_client()
response = client.get("/")
assert response.status_code == 200
assert b"DCP-L2540DW" in response.data
assert client.get("/HomePrinter.ipa").status_code == 401
print("staged app checks: OK")
