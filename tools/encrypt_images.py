#!/usr/bin/env python3
"""
Encrypt images per user and generate a QR code for each one.

Input : a CSV with columns  user_id,image   (image path is relative to the CSV)
Output: softcopy-site/enc/<token>.bin   -> commit + push (public, encrypted)
        qr/<user>.png          -> local only, goes on the printed card
        manifest.csv           -> local only, NEVER commit (holds the QR secrets)

Key   : PBKDF2-HMAC-SHA256( normalize(user_id) [+ QR secret], random salt ) -> AES-256-GCM
File  : "REQ1" | iterations u32be | salt[16] | iv[12] | ciphertext+tag
        The 36-byte header is passed as AES-GCM additional data, so it can't be tampered with.

Usage:
  python tools/encrypt_images.py riders.csv --base-url https://<you>.github.io/<repo>
"""
import argparse
import csv
import mimetypes
import os
import re
import secrets
import struct
import sys
import unicodedata
from pathlib import Path

import qrcode
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"REQ1"
SEP = "\x1f"  # joins ID and QR secret; must match app.js
ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
ROOT = Path(__file__).resolve().parent.parent


def normalize_id(raw: str) -> str:
    """Must stay identical to normalizeId() in docs/app.js."""
    s = unicodedata.normalize("NFKC", raw)
    s = re.sub(r"[\s\-]+", "", s)
    return s.upper()


def password_for(user_id: str, qr_secret: str) -> bytes:
    pw = normalize_id(user_id)
    if qr_secret:
        pw += SEP + qr_secret
    return pw.encode("utf-8")


def encrypt(image: bytes, mime: str, password: bytes, iterations: int) -> bytes:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = PBKDF2HMAC(hashes.SHA256(), 32, salt, iterations).derive(password)
    header = MAGIC + struct.pack(">I", iterations) + salt + iv
    m = mime.encode()
    plaintext = bytes([len(m)]) + m + image
    return header + AESGCM(key).encrypt(iv, plaintext, header)


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)[:80] or "user"


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {r["user_id"]: r for r in csv.DictReader(f)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path, help="CSV with columns user_id,image")
    ap.add_argument("--base-url", required=True, help="GitHub Pages URL, e.g. https://you.github.io/repo")
    ap.add_argument("--iterations", type=int, default=600_000, help="PBKDF2 iterations (default 600000)")
    ap.add_argument("--no-qr-secret", action="store_true",
                    help="Key from user ID only (weaker: anyone can brute-force guessable IDs offline)")
    ap.add_argument("--out", type=Path, default=ROOT, help="Private project root for manifest.csv + qr/ (default: this repo)")
    ap.add_argument("--enc-dir", type=Path, default=None,
                    help="Where to write the PUBLIC encrypted .bin files, e.g. the vault repo's enc/ "
                         "folder (default: <out>/softcopy-site/enc). Keep manifest.csv/qr/ OUT of this dir.")
    args = ap.parse_args()

    enc_dir = args.enc_dir if args.enc_dir else (args.out / "softcopy-site" / "enc")
    qr_dir = args.out / "qr"
    enc_dir.mkdir(parents=True, exist_ok=True)
    qr_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.csv"
    previous = load_manifest(manifest_path)
    base = args.base_url.rstrip("/")

    rows_out = []
    with args.csv.open(newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            uid = (row.get("user_id") or "").strip()
            img_rel = (row.get("image") or "").strip()
            if not uid or not img_rel:
                sys.exit(f"Line {n}: user_id and image are both required")
            img_path = (args.csv.parent / img_rel).resolve()
            mime = mimetypes.guess_type(img_path.name)[0]
            if mime not in ALLOWED_MIME:
                sys.exit(f"Line {n}: {img_rel} must be PNG, JPEG or WebP")

            # Re-running keeps the same token/secret, so already-printed QR codes stay valid.
            prev = previous.get(uid)
            token = prev["token"] if prev else secrets.token_urlsafe(9)
            if args.no_qr_secret:
                qr_secret = ""
            else:
                qr_secret = (prev or {}).get("qr_secret") or secrets.token_urlsafe(16)

            blob = encrypt(img_path.read_bytes(), mime, password_for(uid, qr_secret), args.iterations)
            (enc_dir / f"{token}.bin").write_bytes(blob)

            url = f"{base}/?f={token}" + (f"#k={qr_secret}" if qr_secret else "")
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=12, border=4)
            qr.add_data(url)
            qr.make(fit=True)
            qr_file = qr_dir / f"{safe_name(uid)}.png"
            qr.make_image(fill_color="black", back_color="white").save(qr_file)

            rows_out.append({"user_id": uid, "image": img_rel, "token": token,
                             "qr_secret": qr_secret, "url": url, "qr_png": str(qr_file.relative_to(args.out))})
            print(f"  {uid:<24} -> enc/{token}.bin  qr/{qr_file.name}")

    # Keep earlier entries that weren't in this CSV.
    merged = {**previous, **{r["user_id"]: r for r in rows_out}}
    with manifest_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["user_id", "image", "token", "qr_secret", "url", "qr_png"])
        w.writeheader()
        w.writerows(merged.values())

    print(f"\nEncrypted {len(rows_out)} image(s). Commit {enc_dir} (push it to the PUBLIC vault repo).")
    print("Keep manifest.csv and qr/ private - they are git-ignored.")


if __name__ == "__main__":
    main()
