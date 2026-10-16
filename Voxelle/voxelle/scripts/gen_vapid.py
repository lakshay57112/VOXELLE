"""Create the VAPID key pair that web push needs, and put the public key in .env.

Run once:  python scripts/gen_vapid.py
"""
import base64
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

BASE = Path(__file__).resolve().parent.parent
PEM = BASE / "data" / "vapid_private.pem"
ENV = BASE / ".env"


def main() -> None:
    PEM.parent.mkdir(exist_ok=True)
    if PEM.exists():
        key = serialization.load_pem_private_key(PEM.read_bytes(), password=None)
        print(f"Using existing key at {PEM}")
    else:
        key = ec.generate_private_key(ec.SECP256R1())
        PEM.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        PEM.chmod(0o600)
        print(f"Wrote private key to {PEM} (keep it secret)")

    raw = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    public = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    text = ENV.read_text() if ENV.exists() else (BASE / ".env.example").read_text()
    if re.search(r"^VAPID_PUBLIC_KEY=.*$", text, flags=re.M):
        text = re.sub(r"^VAPID_PUBLIC_KEY=.*$", f"VAPID_PUBLIC_KEY={public}", text, flags=re.M)
    else:
        text += f"\nVAPID_PUBLIC_KEY={public}\n"
    ENV.write_text(text)
    print("VAPID_PUBLIC_KEY saved to .env")
    print("Also set VAPID_SUBJECT in .env to your own email (mailto:you@gmail.com).")


if __name__ == "__main__":
    main()
