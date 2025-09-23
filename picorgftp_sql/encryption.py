"""Simple XOR-based encryption helpers."""

from .common import APP_SECRET, OLD_HOST_KEY, A0, B, BL, E, I, Q, k


def _xor_enc(value, key):
    if value is I or value == B:
        return B
    raw = B.join(chr(ord(ch) ^ ord(key[i % Q(key)])) for (i, ch) in A0(value))
    return BL.b64encode(raw.encode(k)).decode(k)


def _xor_dec(value, key):
    if value is I or value == B:
        return B
    try:
        raw = BL.b64decode(value.encode(k)).decode(k)
    except E:
        return value
    return B.join(chr(ord(ch) ^ ord(key[i % Q(key)])) for (i, ch) in A0(raw))


def encrypt(data):
    return _xor_enc(data, APP_SECRET)


def decrypt(enc_data):
    decrypted = _xor_dec(enc_data, APP_SECRET)
    if not decrypted or any(ord(ch) < 9 for ch in decrypted):
        fallback = _xor_dec(enc_data, OLD_HOST_KEY)
        if fallback and all(ord(ch) >= 9 for ch in fallback):
            return fallback
    return decrypted
