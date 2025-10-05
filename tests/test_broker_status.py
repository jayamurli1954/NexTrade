from config.credentials_manager import SecureCredentialsManager
from data_provider.angel_provider import AngelProvider

# Load saved credentials
cm = SecureCredentialsManager("config")
ok, creds = cm.load_credentials()
print("creds loaded:", ok)

# Toggle this: True = Paper trading, False = Live trading
USE_PAPER_MODE = False   # ⬅️ change to False for real Angel One login

p = AngelProvider(paper_mode=USE_PAPER_MODE)

p.set_credentials(
    client_code=creds.get("client_code", ""),
    api_key=creds.get("api_key", ""),
    password=creds.get("password", ""),
    totp_secret=creds.get("totp_secret", ""),
)

print("connect:", p.connect())
print("profile:", p.get_profile())
print("funds:", p.get_funds())
print("holdings:", p.get_holdings())
print("ltp_bulk:", p.get_ltp_bulk(["RELIANCE-EQ", "TCS-EQ", "INFY-EQ"]))

