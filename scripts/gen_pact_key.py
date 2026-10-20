#!/usr/bin/env python3
"""Generate the PACT signing key and sub secret, optionally storing them in SSM as SecureStrings.

    python scripts/gen_pact_key.py                    # print both (no AWS calls)
    python scripts/gen_pact_key.py --store /shopping-assistant/pact [--profile btaws]

Writes <prefix>/private-jwk and <prefix>/sub-secret. The private key is never printed
when --store is used. Existing parameters are not overwritten unless --overwrite is given
(rotating the sub secret changes every user's PACT identity).
"""
import argparse
import base64
import json
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def b64url_int(n: int, length: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


def generate_private_jwk() -> dict:
    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.private_numbers()
    pub = numbers.public_numbers
    return {"kty": "EC", "crv": "P-256", "x": b64url_int(pub.x, 32), "y": b64url_int(pub.y, 32),
            "d": b64url_int(numbers.private_value, 32)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", metavar="PREFIX", help="SSM parameter prefix, e.g. /shopping-assistant/pact")
    parser.add_argument("--profile")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    jwk = json.dumps(generate_private_jwk(), separators=(",", ":"))
    sub_secret = secrets.token_urlsafe(32)

    if not args.store:
        print(f"PACT_PRIVATE_JWK={jwk}")
        print(f"PACT_SUB_SECRET={sub_secret}")
        return

    import boto3
    from botocore.exceptions import ClientError

    ssm = boto3.Session(profile_name=args.profile, region_name=args.region).client("ssm")
    prefix = args.store.rstrip("/")
    for name, value in ((f"{prefix}/private-jwk", jwk), (f"{prefix}/sub-secret", sub_secret)):
        try:
            ssm.put_parameter(Name=name, Value=value, Type="SecureString", Overwrite=args.overwrite)
            print(f"stored {name}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterAlreadyExists":
                print(f"skipped {name}: already exists (use --overwrite to replace)")
            else:
                raise


if __name__ == "__main__":
    main()
