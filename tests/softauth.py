"""A software WebAuthn authenticator (ES256, attestation 'none') for end-to-end tests.

It produces byte-for-byte spec-shaped registration/assertion responses with real signatures, so the
real py_webauthn verifier can be exercised without a browser or hardware key.
"""
import hashlib
import json
import os
import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from tests.auth_helpers import b64

FLAG_UP, FLAG_UV, FLAG_AT = 0x01, 0x04, 0x40


# ---- minimal CBOR (just what WebAuthn needs)
def cbor(o):
    def head(major, n):
        if n < 24: return bytes([major << 5 | n])
        if n < 256: return bytes([major << 5 | 24, n])
        if n < 65536: return bytes([major << 5 | 25]) + struct.pack(">H", n)
        return bytes([major << 5 | 26]) + struct.pack(">I", n)
    if isinstance(o, bool): raise TypeError
    if isinstance(o, int): return head(0, o) if o >= 0 else head(1, -1 - o)
    if isinstance(o, bytes): return head(2, len(o)) + o
    if isinstance(o, str): b = o.encode(); return head(3, len(b)) + b
    if isinstance(o, list): return head(4, len(o)) + b"".join(cbor(i) for i in o)
    if isinstance(o, dict): return head(5, len(o)) + b"".join(cbor(k) + cbor(v) for k, v in o.items())
    raise TypeError(type(o))


def cbor_decode(data, i=0):
    ib = data[i]; major, ai = ib >> 5, ib & 31; i += 1
    if ai < 24: n = ai
    elif ai == 24: n = data[i]; i += 1
    elif ai == 25: n = struct.unpack(">H", data[i:i + 2])[0]; i += 2
    else: n = struct.unpack(">I", data[i:i + 4])[0]; i += 4
    if major == 0: return n, i
    if major == 1: return -1 - n, i
    if major == 2: return data[i:i + n], i + n
    if major == 3: return data[i:i + n].decode(), i + n
    if major == 4:
        out = []
        for _ in range(n): v, i = cbor_decode(data, i); out.append(v)
        return out, i
    if major == 5:
        out = {}
        for _ in range(n):
            k, i = cbor_decode(data, i); v, i = cbor_decode(data, i); out[k] = v
        return out, i
    raise ValueError(major)


def _unb64(s):
    import base64
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class SoftAuthenticator:
    def __init__(self, rp_id="zeim.test", origin="https://zeim.test", user_handle=None):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(32)
        self.counter = 0
        self.user_handle = user_handle

    @property
    def id(self):
        return b64(self.cred_id)

    def _cose_key(self):
        n = self.key.public_key().public_numbers()
        return cbor({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})

    def _client_data(self, typ, challenge_b64, origin=None):
        return json.dumps({"type": typ, "challenge": challenge_b64, "origin": origin or self.origin,
                           "crossOrigin": False}, separators=(",", ":")).encode()

    def create(self, options, origin=None, challenge=None):
        """options = the creation options JSON the server sent to the browser."""
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        auth_data = (rp_hash + bytes([FLAG_UP | FLAG_UV | FLAG_AT]) + struct.pack(">I", 0) + b"\0" * 16
                     + struct.pack(">H", len(self.cred_id)) + self.cred_id + self._cose_key())
        att = cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cd = self._client_data("webauthn.create", challenge or options["challenge"], origin)
        return {"id": self.id, "rawId": self.id, "type": "public-key", "clientExtensionResults": {},
                "response": {"clientDataJSON": b64(cd), "attestationObject": b64(att), "transports": ["internal"]}}

    def get(self, options, origin=None, challenge=None, counter=None, sign_with=None):
        self.counter = self.counter + 1 if counter is None else counter
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        auth_data = rp_hash + bytes([FLAG_UP | FLAG_UV]) + struct.pack(">I", self.counter)
        cd = self._client_data("webauthn.get", challenge or options["challenge"], origin)
        sig = (sign_with or self.key).sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {"id": self.id, "rawId": self.id, "type": "public-key", "clientExtensionResults": {},
                "response": {"authenticatorData": b64(auth_data), "clientDataJSON": b64(cd), "signature": b64(sig),
                             "userHandle": b64(self.user_handle) if self.user_handle else None}}


def selfcheck_registration(cred, rp_id, expected_challenge_b64, origin):
    """Independent re-derivation of what a verifier must check (used to validate this fixture itself)."""
    cd = json.loads(_unb64(cred["response"]["clientDataJSON"]))
    assert cd["type"] == "webauthn.create" and cd["challenge"] == expected_challenge_b64 and cd["origin"] == origin
    att, _ = cbor_decode(_unb64(cred["response"]["attestationObject"]))
    assert att["fmt"] == "none"
    ad = att["authData"]
    assert ad[:32] == hashlib.sha256(rp_id.encode()).digest() and ad[32] & FLAG_AT and ad[32] & FLAG_UP
    idlen = struct.unpack(">H", ad[53:55])[0]
    cred_id = ad[55:55 + idlen]
    assert b64(cred_id) == cred["id"]
    key, _ = cbor_decode(ad[55 + idlen:])
    return ec.EllipticCurvePublicNumbers(int.from_bytes(key[-2], "big"), int.from_bytes(key[-3], "big"), ec.SECP256R1()).public_key()


def selfcheck_assertion(cred, public_key, rp_id, expected_challenge_b64, origin, min_counter):
    r = cred["response"]
    cd_raw = _unb64(r["clientDataJSON"]); cd = json.loads(cd_raw)
    assert cd["type"] == "webauthn.get" and cd["challenge"] == expected_challenge_b64 and cd["origin"] == origin
    ad = _unb64(r["authenticatorData"])
    assert ad[:32] == hashlib.sha256(rp_id.encode()).digest() and ad[32] & FLAG_UP
    assert struct.unpack(">I", ad[33:37])[0] >= min_counter
    public_key.verify(_unb64(r["signature"]), ad + hashlib.sha256(cd_raw).digest(), ec.ECDSA(hashes.SHA256()))   # raises if invalid
