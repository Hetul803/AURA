#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate AURA vendor signing keys or signed private-alpha license tokens.')
    parser.add_argument('--key-dir', default='license_keys', help='Directory for vendor_private.pem and vendor_public.pem')
    parser.add_argument('--email', help='Account email for a signed license token')
    parser.add_argument('--tier', default='private_alpha')
    parser.add_argument('--license-id', default='')
    parser.add_argument('--expires-at', default='')
    parser.add_argument('--seats', type=int, default=1)
    args = parser.parse_args()

    key_dir = Path(args.key_dir)
    key_dir.mkdir(parents=True, exist_ok=True)
    private_path = key_dir / 'vendor_private.pem'
    public_path = key_dir / 'vendor_public.pem'
    if not private_path.exists():
        private_key = ed25519.Ed25519PrivateKey.generate()
        private_path.write_bytes(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        public_path.write_bytes(private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        private_path.chmod(0o600)
        print(f'Generated vendor keys in {key_dir}')
        print('Never ship vendor_private.pem inside the app.')
    else:
        private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        print(f'Using existing vendor keys in {key_dir}')

    print('\nPublic key for app distribution:')
    print(public_path.read_text(encoding='utf-8'))

    if args.email:
        payload = {
            'license_id': args.license_id or f'lic_{args.email.replace("@", "_at_")}',
            'account_email': args.email,
            'tier': args.tier,
            'seats': args.seats,
            'issuer': 'AURA private-alpha license generator',
            'features': {
                'helper': True,
                'guardian': True,
                'encrypted_memory': True,
                'cryptographic_identity': True,
                'overlay': True,
            },
        }
        if args.expires_at:
            payload['expires_at'] = args.expires_at
        body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')
        signature = private_key.sign(body)
        print('\nSigned license token:')
        print(f'{b64url(body)}.{b64url(signature)}')


if __name__ == '__main__':
    main()
