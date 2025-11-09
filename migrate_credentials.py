"""
CRITICAL SECURITY FIX: Migrate Credentials from Plain JSON

This script migrates credentials from config.json to encrypted storage
and backs up the old file.

Usage:
    python migrate_credentials.py
"""

import os
import json
import shutil
from datetime import datetime
from config.credentials_manager import SecureCredentialsManager

def migrate_credentials():
    """Migrate credentials from config.json to encrypted storage"""

    config_file = "config.json"
    backup_file = f"config.json.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Check if config.json exists
    if not os.path.exists(config_file):
        print(f"✅ No {config_file} found - credentials may already be migrated")
        return True

    try:
        # Read current config
        with open(config_file, 'r') as f:
            config = json.load(f)

        # Extract credentials
        api_key = config.get('api_key', '')
        client_id = config.get('client_id', '')
        password = config.get('password', '')
        totp_token = config.get('totp_token', '')

        # Check if credentials exist
        if not all([api_key, client_id, password, totp_token]):
            print("⚠️  No valid credentials found in config.json")
            return False

        print(f"📋 Found credentials in {config_file}")
        print(f"   API Key: {api_key[:10]}...")
        print(f"   Client ID: {client_id}")

        # Save to encrypted storage
        print("\n🔐 Migrating to encrypted storage...")
        mgr = SecureCredentialsManager()
        success, message = mgr.save_credentials(
            api_key=api_key,
            client_code=client_id,
            password=password,
            totp_secret=totp_token
        )

        if not success:
            print(f"❌ Migration failed: {message}")
            return False

        # Verify the credentials were saved correctly
        print("\n✓ Verifying encrypted storage...")
        loaded_success, loaded_creds = mgr.load_credentials()

        if not loaded_success:
            print("❌ Verification failed - could not load credentials")
            return False

        if loaded_creds.get('api_key') != api_key:
            print("❌ Verification failed - credentials don't match")
            return False

        print("✓ Verification successful")

        # Backup the old config.json
        print(f"\n💾 Creating backup: {backup_file}")
        shutil.copy2(config_file, backup_file)

        # Remove sensitive data from config.json
        print(f"\n🧹 Removing credentials from {config_file}")
        config_cleaned = {
            "initial_capital": config.get("initial_capital", 100000),
            "risk_per_trade": config.get("risk_per_trade", 2),
            "auto_trading": config.get("auto_trading", False),
            "_comment": "Credentials moved to encrypted storage. See backup file if needed."
        }

        with open(config_file, 'w') as f:
            json.dump(config_cleaned, f, indent=4)

        print("\n✅ MIGRATION COMPLETE!")
        print(f"\n📌 Summary:")
        print(f"   ✓ Credentials encrypted and stored securely")
        print(f"   ✓ Backup created: {backup_file}")
        print(f"   ✓ {config_file} cleaned (credentials removed)")
        print(f"\n⚠️  IMPORTANT:")
        print(f"   1. Test that login works with the encrypted credentials")
        print(f"   2. If successful, you can delete: {backup_file}")
        print(f"   3. Never commit {backup_file} to git!")

        return True

    except Exception as e:
        print(f"❌ Migration error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*70)
    print("  CRITICAL SECURITY FIX: Credential Migration")
    print("="*70)
    print()
    print("This script will:")
    print("  1. Read credentials from config.json")
    print("  2. Encrypt and store them securely")
    print("  3. Create backup of config.json")
    print("  4. Remove credentials from config.json")
    print()

    response = input("Continue? (yes/no): ").strip().lower()

    if response == 'yes':
        print()
        success = migrate_credentials()

        if success:
            print("\n" + "="*70)
            print("  Migration completed successfully!")
            print("="*70)
        else:
            print("\n" + "="*70)
            print("  Migration failed - credentials NOT removed")
            print("="*70)
    else:
        print("\n❌ Migration cancelled")
