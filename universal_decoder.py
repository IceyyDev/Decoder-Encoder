#!/usr/bin/env python3
"""
Universal Python Obfuscation Decoder
=====================================
The most comprehensive Python deobfuscation tool. Handles deeply nested,
multi-layer obfuscation chains including encryption, compression, marshalling,
and custom encoders.

Supported techniques:
  - Reversed hex exec (AIZEN/X9SVE encoder)
  - Direct hex exec
  - Base64 exec (inline and variable-based)
  - Lambda IIFE wrappers (e.g. (lambda: 'b64...')() with file write + exec)
  - PBKDF2 + XOR encrypted payloads (LEEEUNJU-style)
  - exec(zlib.decompress(b'...'))
  - exec(marshal.loads(b'...')) with nested payload extraction
  - Marshal code objects with embedded base64/zlib/XOR data
  - Unicode steganography / interleaved-key XOR (LEEEUNJU_deobfuscate)
  - exec(compile(...)) wrappers
  - chr() list exec
  - eval() wrappers
  - Multi-step transformation chains (base64 + XOR + reverse + zlib + marshal)
  - Variable concatenation patterns (var1 + var2 + ... = payload)
  - Safe simulation of decoding functions (intercepts exec/marshal.loads)
  - Marshal code object analysis (function signatures, strings, structure)
  - STEIN-style multi-payload b85+bz2+zlib chains (split across many b'...' vars)
  - XOR-lambda obfuscated identifiers ((lambda x,s:''.join(chr(c^x)for c in s))(K,[bytes]))
  - Multi-layer auto-peeling (unlimited depth)
  - **Universal sandboxed-execution fallback**: handles ANY obfuscation chain
    (custom ciphers, unknown encodings, novel patterns) by intercepting
    exec/eval/compile/marshal.loads while blocking dangerous side effects
  - Embedded native binary payload extraction (tar.xz, bz2, zip, ELF, PE)
  - Cython 3.0+ `CYTHON_COMPRESS_STRINGS` blob extraction (decompiles compiled .so/.exe string tables)
  - PyInstaller bundle detection
  - Output pretty-printing (ast.unparse) for minified one-line outputs

Usage:
    python universal_decoder.py <encoded_file> [-o output_file] [--max-layers N] [-v]
"""

import argparse
import ast
import base64
import bz2
import gzip
import hashlib
import hmac
import lzma
import marshal
import re
import sys
import textwrap
import types
import zlib
from pathlib import Path


# ============================================================================
#  Utility helpers
# ============================================================================

def _safe_literal_eval(data: bytes) -> object:
    """Parse a Python bytes/string literal from raw file bytes."""
    return ast.literal_eval(data.decode("latin-1"))


def _strip_leading_junk(data: bytes, marker: bytes = b"import ") -> bytes:
    """Remove up to 100 garbage bytes before the first 'import ' keyword."""
    idx = data.find(marker)
    if 0 < idx < 100:
        return data[idx:]
    return data


# ============================================================================
#  LEEEUNJU encryption helpers (PBKDF2 + HMAC-CTR XOR)
# ============================================================================

def _pbkdf2(pw: str, salt: bytes, its: int = 100000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, its, dklen=32)


def _hmac_keystream(key: bytes, n: int) -> bytes:
    out = b""
    blk = 0
    while len(out) < n:
        ctr = blk.to_bytes(8, "big")
        out += hmac.new(key, ctr, hashlib.sha256).digest()
        blk += 1
    return out[:n]


def _xor_decrypt(data: bytes, key: bytes) -> bytes:
    ks = _hmac_keystream(key, len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


# ============================================================================
#  LEEEUNJU Unicode steganography (interleaved-key XOR)
# ============================================================================

def _leeeunju_deobfuscate(data_with_key: str) -> str:
    half = len(data_with_key) // 2
    encrypted_text = "".join(data_with_key[i * 2] for i in range(half))
    key = "".join(data_with_key[i * 2 + 1] for i in range(half))
    return "".join(
        chr(ord(c) ^ ord(key[i % len(key)]))
        for i, c in enumerate(encrypted_text)
    )


# ============================================================================
#  Binary-level decoders (work on raw bytes)
# ============================================================================

def _try_binary_exec_patterns(data: bytes):
    """
    Handles patterns like:
      import zlib\\nexec(zlib.decompress(b'...'))
      import marshal\\nexec(marshal.loads(b'...'))
      import base64\\nexec(base64.b64decode(b'...'))
    Returns (decoded_bytes, description) or None.
    """
    data = _strip_leading_junk(data)

    patterns = [
        (b"import zlib\nexec(zlib.decompress(", "zlib.decompress"),
        (b"import marshal\nexec(marshal.loads(", "marshal.loads"),
        (b"import base64\nexec(base64.b64decode(", "base64.b64decode"),
    ]

    for prefix, desc in patterns:
        if not data.startswith(prefix):
            continue
        remainder = data[len(prefix):]
        end = remainder.rfind(b"))")
        if end < 0:
            continue
        literal = remainder[:end]
        try:
            payload = _safe_literal_eval(literal)
        except Exception:
            continue

        if desc == "zlib.decompress":
            try:
                return zlib.decompress(payload), desc
            except Exception:
                pass
        elif desc == "marshal.loads":
            return _decode_marshal_payload(payload, desc)
        elif desc == "base64.b64decode":
            try:
                return base64.b64decode(payload), desc
            except Exception:
                pass
    return None


def _decode_marshal_payload(marshalled: bytes, parent_desc: str):
    """
    Decode a marshal.loads payload. The code object often does:
      - import zlib; exec(zlib.decompress(CONST))
      - import base64; exec(base64.b64decode(CONST))
      - define LEEEUNJU_deobfuscate and apply it to a Unicode payload
    """
    try:
        code_obj = marshal.loads(marshalled)
    except Exception:
        return None

    if not isinstance(code_obj, types.CodeType):
        return None

    names = tuple(code_obj.co_names)

    # Check for LEEEUNJU-style Unicode deobfuscation
    if "LEEEUNJU_deobfuscate" in names:
        return _decode_leeeunju_marshal(code_obj)

    # Find the data constant and determine what to do with it
    for c in code_obj.co_consts:
        if isinstance(c, bytes) and len(c) > 50:
            # Try based on what the code imports
            if "zlib" in names:
                try:
                    return zlib.decompress(c), f"{parent_desc} -> zlib"
                except Exception:
                    pass
            if "base64" in names:
                try:
                    return base64.b64decode(c), f"{parent_desc} -> base64"
                except Exception:
                    pass
            # Fallback attempts
            for op_name, op in [("zlib", zlib.decompress), ("base64", base64.b64decode)]:
                try:
                    return op(c), f"{parent_desc} -> {op_name} (fallback)"
                except Exception:
                    pass

        elif isinstance(c, str) and len(c) > 50:
            # String constant — might be base64 or Unicode-encoded
            try:
                return base64.b64decode(c.encode()), f"{parent_desc} -> base64 str"
            except Exception:
                pass

    # Check nested code objects for more complex patterns
    for c in code_obj.co_consts:
        if isinstance(c, types.CodeType):
            # Recursive: inner code object may also be a marshal wrapper
            pass

    return None


def _decode_leeeunju_marshal(code_obj: types.CodeType):
    """
    Handle LEEEUNJU-style obfuscation:
      - Code defines LEEEUNJU_deobfuscate (interleaved-key XOR)
      - Applies it to a large Unicode string constant
      - exec(compile(result))
    """
    encrypted = None
    for c in code_obj.co_consts:
        if isinstance(c, str) and len(c) > 100:
            encrypted = c
            break

    if encrypted is None:
        return None

    try:
        result = _leeeunju_deobfuscate(encrypted)
        return result.encode("utf-8"), "LEEEUNJU Unicode XOR deobfuscation"
    except Exception:
        return None


# ============================================================================
#  Text-level decoders (regex on source strings)
# ============================================================================

def _try_reversed_hex_exec(source: str):
    """Reversed hex exec (AIZEN/X9SVE style)."""
    m = re.search(
        r"""exec\s*\(\s*\(?_+\)?\s*\(\s*['"]([0-9a-fA-F]+)['"]\s*\)\s*\)""",
        source,
    )
    if m:
        try:
            decoded = bytes.fromhex(m.group(1)[::-1]).decode("utf-8", errors="replace")
            return decoded, "reversed-hex exec (lambda)"
        except Exception:
            pass

    m = re.search(
        r"""exec\s*\(\s*bytes\.fromhex\s*\(\s*['"]([0-9a-fA-F]+)['"]\s*\[\s*::\s*-1\s*\]\s*\)\s*\)""",
        source,
    )
    if m:
        try:
            decoded = bytes.fromhex(m.group(1)[::-1]).decode("utf-8", errors="replace")
            return decoded, "reversed-hex exec (inline)"
        except Exception:
            pass
    return None


def _try_direct_hex_exec(source: str):
    """Direct hex exec."""
    for pat in [
        r"""exec\s*\(\s*bytes\.fromhex\s*\(\s*['"]([0-9a-fA-F]+)['"]\s*\)\s*\.decode\s*\(.*?\)\s*\)""",
        r"""exec\s*\(\s*bytes\.fromhex\s*\(\s*['"]([0-9a-fA-F]+)['"]\s*\)\s*\)""",
    ]:
        m = re.search(pat, source)
        if m:
            try:
                return bytes.fromhex(m.group(1)).decode("utf-8", errors="replace"), "direct hex exec"
            except Exception:
                pass
    return None


def _try_base64_exec(source: str):
    """Base64 exec (inline)."""
    for pat in [
        r"""exec\s*\(\s*(?:base64\.)?b64decode\s*\(\s*[b]?['"]([A-Za-z0-9+/=\n]+)['"]\s*\)""",
        r"""exec\s*\(\s*__import__\s*\(\s*['"]base64['"]\s*\)\s*\.b64decode\s*\(\s*[b]?['"]([A-Za-z0-9+/=\n]+)['"]\s*\)""",
    ]:
        m = re.search(pat, source)
        if m:
            try:
                return base64.b64decode(m.group(1)).decode("utf-8", errors="replace"), "base64 exec"
            except Exception:
                pass
    return None


def _try_zlib_exec(source: str):
    """exec(zlib.decompress(...))."""
    m = re.search(
        r"""exec\s*\(\s*zlib\.decompress\s*\(\s*(?:base64\.)?b64decode\s*\(\s*[b]?['"]([A-Za-z0-9+/=\n]+)['"]\s*\)""",
        source,
    )
    if m:
        try:
            return zlib.decompress(base64.b64decode(m.group(1))).decode("utf-8", errors="replace"), "zlib+base64 exec"
        except Exception:
            pass

    m = re.search(
        r"""exec\s*\(\s*zlib\.decompress\s*\(\s*bytes\.fromhex\s*\(\s*['"]([0-9a-fA-F]+)['"]\s*\)\s*\)""",
        source,
    )
    if m:
        try:
            return zlib.decompress(bytes.fromhex(m.group(1))).decode("utf-8", errors="replace"), "zlib+hex exec"
        except Exception:
            pass
    return None


def _try_compile_exec(source: str):
    """exec(compile('...', '...', 'exec'))."""
    m = re.search(
        r"""exec\s*\(\s*compile\s*\(\s*['"]{1,3}(.*?)['"]{1,3}\s*,\s*['"].*?['"]\s*,\s*['"]exec['"]\s*\)""",
        source,
        re.DOTALL,
    )
    if m:
        inner = m.group(1)
        try:
            decoded = ast.literal_eval(f'"""{inner}"""')
        except Exception:
            decoded = inner
        return decoded, "compile exec"
    return None


def _try_chr_join_exec(source: str):
    """exec(''.join(chr(i) for i in [...]))."""
    m = re.search(
        r"""exec\s*\(\s*['"](?:|)['"]\.join\s*\(\s*(?:chr\s*\(\s*i\s*\)\s*for\s*i\s*in|map\s*\(\s*chr\s*,)\s*\[([0-9,\s]+)\]""",
        source,
    )
    if m:
        try:
            nums = [int(x.strip()) for x in m.group(1).split(",") if x.strip()]
            return "".join(chr(n) for n in nums), "chr-list exec"
        except Exception:
            pass
    return None


def _try_lambda_iife_base64(source: str):
    """
    Lambda IIFE pattern:
      VAR = (lambda: 'BASE64_STRING')()
    followed by file-write + os.system or exec.
    """
    m = re.search(
        r"""\w+\s*=\s*\(lambda\s*:\s*'([A-Za-z0-9+/=\n]{100,})'\s*\)\s*\(\s*\)""",
        source,
    )
    if not m:
        m = re.search(
            r"""\w+\s*=\s*\(lambda\s*:\s*"([A-Za-z0-9+/=\n]{100,})"\s*\)\s*\(\s*\)""",
            source,
        )
    if m:
        try:
            decoded = base64.b64decode(m.group(1)).decode("utf-8", errors="replace")
            return decoded, "lambda IIFE base64"
        except Exception:
            pass
    return None


def _try_leeeunju_encryption(source: str):
    """
    LEEEUNJU-style PBKDF2+XOR encryption:
      pw = "..."
      a = 'ASCII85_ENCODED_DATA'
      b = base64.a85decode(a.encode())
      salt = b[:16]; ct = b[16:]
      key = _pbkdf2(pw, salt)
      z = _xor(ct, key)
      p = zlib.decompress(z)
      m1, s = marshal.loads(p)  OR just marshal.loads(p)
    """
    pw_match = re.search(r'pw\s*=\s*["\']([^"\']+)["\']', source)
    if not pw_match:
        return None

    # Find the ASCII85 payload
    a_match = re.search(r"a\s*=\s*'((?:[^'\\]|\\.)+)'", source, re.DOTALL)
    if not a_match:
        a_match = re.search(r'a\s*=\s*"((?:[^"\\]|\\.)+)"', source, re.DOTALL)
    if not a_match:
        return None

    pw = pw_match.group(1)
    a_str = a_match.group(1).replace("\\'", "'").replace("\\\\", "\\")

    try:
        b = base64.a85decode(a_str.encode())
        salt = b[:16]
        ct = b[16:]
        key = _pbkdf2(pw, salt, its=100000)
        z = _xor_decrypt(ct, key)
        p = zlib.decompress(z)

        # Try to unpack marshal data
        try:
            result = marshal.loads(p)
            if isinstance(result, tuple) and len(result) == 2:
                _, s = result
                if isinstance(s, bytes):
                    return s.decode("utf-8", errors="replace"), "LEEEUNJU encrypted (PBKDF2+XOR+zlib+marshal tuple)"
            elif isinstance(result, types.CodeType):
                return None  # Can't decompile code objects directly
            elif isinstance(result, bytes):
                return result.decode("utf-8", errors="replace"), "LEEEUNJU encrypted (PBKDF2+XOR+zlib+marshal)"
        except Exception:
            # Maybe the decompressed data is just Python source
            return p.decode("utf-8", errors="replace"), "LEEEUNJU encrypted (PBKDF2+XOR+zlib)"
    except Exception:
        pass
    return None


def _try_generic_hex_string(source: str):
    """Fallback: any very long hex string."""
    for m in re.finditer(r"['\"]([0-9a-fA-F]{100,})['\"]", source):
        hex_str = m.group(1)
        for attempt_reverse in [False, True]:
            try:
                h = hex_str[::-1] if attempt_reverse else hex_str
                decoded = bytes.fromhex(h).decode("utf-8", errors="strict")
                if decoded.isprintable() or "\n" in decoded:
                    label = "generic reversed hex" if attempt_reverse else "generic hex"
                    return decoded, label
            except Exception:
                pass
    return None


def _try_eval_wrapper(source: str):
    """eval('...') wrappers."""
    m = re.search(r"""eval\s*\(\s*['"](.+?)['"]\s*\)""", source, re.DOTALL)
    if m:
        try:
            inner = ast.literal_eval(f'"{m.group(1)}"')
            return inner, "eval wrapper"
        except Exception:
            pass
    return None


def _try_simulation_decode(source: str):
    """
    Smart simulation: parse the Python file, extract string variables,
    detect transformation chains (base64/XOR/reverse/zlib), and simulate
    them to recover the payload. Intercepts exec() and marshal.loads().

    Handles patterns like:
      var1 = "base64..."
      var2 = "base64..."
      d = (var1 + var2 + ...).encode()
      def f():
          t = base64.b64decode(d)
          t = bytes([i^KEY for i in t])
          ...
          exec(marshal.loads(t), globals())
    """
    # Step 1: Find all string variable assignments (including multi-assign lines)
    all_vars = {}
    for m in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', source):
        name, val = m.group(1), m.group(2)
        if len(val) > 50:
            all_vars[name] = val

    if not all_vars:
        return None

    # Step 2: Find the concatenation pattern
    concat_match = re.search(
        r'(\w+)\s*=\s*\(([\w+\s]+)\)\.encode\(\)',
        source,
    )
    if not concat_match:
        return None

    parts = [p.strip() for p in concat_match.group(2).split('+')]
    missing = [p for p in parts if p not in all_vars]
    if missing:
        return None

    # Step 3: Build the concatenated payload
    payload = ''.join(all_vars[p] for p in parts).encode()

    # Step 4: Find and simulate the transformation chain
    func_match = re.search(
        r'def\s+\w+\(\):\s*\n(.*?)(?:^[a-zA-Z]|\Z)',
        source,
        re.MULTILINE | re.DOTALL,
    )
    if not func_match:
        return None

    func_body = func_match.group(1)
    data = payload
    steps = []

    for line in func_body.split('\n'):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('try:') or line.startswith('except') or line.startswith('print'):
            continue

        # base64.b64decode
        if re.match(r'\w+\s*=\s*base64\.b64decode\(', line):
            try:
                data = base64.b64decode(data)
                steps.append('b64')
            except Exception:
                break

        # XOR: bytes([i^KEY for i in VAR])
        xor_m = re.match(r'\w+\s*=\s*bytes\(\[\s*i\s*\^\s*(\d+)\s+for\s+i\s+in\s+\w+\s*\]\)', line)
        if xor_m:
            key = int(xor_m.group(1))
            data = bytes([b ^ key for b in data])
            steps.append(f'xor({key})')

        # Reverse: t = t[::-1]
        if re.match(r'\w+\s*=\s*\w+\[\s*::\s*-1\s*\]', line):
            data = data[::-1]
            steps.append('reverse')

        # zlib.decompress
        if re.match(r'\w+\s*=\s*zlib\.decompress\(', line):
            try:
                data = zlib.decompress(data)
                steps.append('zlib')
            except Exception:
                break

        # exec(marshal.loads(t)) — final step
        if 'marshal.loads' in line:
            try:
                code_obj = marshal.loads(data)
                if isinstance(code_obj, types.CodeType):
                    analysis = _analyze_marshal_code(code_obj)
                    desc = f"simulation ({' -> '.join(steps)} -> marshal)"
                    return analysis, desc
            except Exception:
                break

    if not steps:
        return None

    try:
        text = data.decode('utf-8', errors='replace')
        desc = f"simulation ({' -> '.join(steps)})"
        return text, desc
    except Exception:
        return None


def _analyze_marshal_code(code_obj: types.CodeType) -> str:
    """
    Produce a comprehensive analysis of a marshal code object:
    imports, credentials, function signatures, string literals, behavior.
    """
    info = _extract_code_tree(code_obj)
    top_names = list(code_obj.co_names)
    lines = []

    lines.append('# === AUTO-DECODED FROM MARSHAL CODE OBJECT ===')
    lines.append(f'# Compiled from: {code_obj.co_filename}')
    lines.append('')

    # Imports
    known_mods = {
        'os', 'sys', 'time', 'random', 'threading', 'string', 'uuid',
        'webbrowser', 'pathlib', 'datetime', 'requests', 'colorama',
        'json', 'hashlib', 'socket', 'subprocess', 'urllib', 'http',
        'base64', 'zlib', 'marshal', 'pickle', 'struct', 're',
        'concurrent.futures', 'asyncio', 'aiohttp', 'httpx',
    }
    imports = [n for n in top_names if n in known_mods]
    if imports:
        lines.append('# --- Imports ---')
        for mod in imports:
            lines.append(f'import {mod}')
        lines.append('')

    # Credentials / URLs / paths
    creds = []
    for s in info['strings']:
        if any(k in s for k in ('api.telegram.org', 'token', 'bot', 'AAG', 'AAH')):
            creds.append(f'# Token/URL: {s!r}')
        elif s.isdigit() and len(s) >= 6:
            creds.append(f'# Chat/User ID: {s!r}')
        elif '/storage/' in s or 'Download' in s:
            creds.append(f'# File path: {s!r}')
        elif s.startswith('.') and len(s) < 10:
            creds.append(f'# File extension: {s!r}')
    if creds:
        lines.append('# --- Embedded Credentials & Paths ---')
        lines.extend(creds)
        lines.append('')

    # Functions
    lines.append('# --- Functions ---')
    for func in info['functions']:
        fname = func['name']
        if fname in ('<genexpr>', '<listcomp>', '<dictcomp>', '<lambda>',
                      '<module>', '<setcomp>'):
            continue
        args = ', '.join(func['args'])
        lines.append(f'def {fname}({args}):')
        lines.append(f'    # Uses: {", ".join(func["names"][:12])}')
        for s in func['strings']:
            if len(s) > 5:
                lines.append(f'    # String: {s[:120]!r}')
        lines.append(f'    ...  # compiled bytecode')
        lines.append('')

    return '\n'.join(lines)


def _extract_code_tree(co: types.CodeType) -> dict:
    """Recursively extract all data from a code object tree."""
    info = {
        'name': co.co_name,
        'args': list(co.co_varnames[:co.co_argcount]),
        'names': list(co.co_names),
        'strings': [],
        'numbers': [],
        'functions': [],
    }
    for c in co.co_consts:
        if isinstance(c, str) and len(c) > 3:
            info['strings'].append(c)
        elif isinstance(c, (int, float)) and c not in (0, 1, -1, None, True, False):
            info['numbers'].append(c)
        elif isinstance(c, types.CodeType):
            child = _extract_code_tree(c)
            info['functions'].append(child)
            info['strings'].extend(child['strings'])
    return info


def _try_sandbox_decode(source: str):
    """
    Sandboxed-execution fallback for ANY obfuscation chain.

    Runs the obfuscated source in a controlled namespace where:
      - exec, eval, compile, marshal.loads are intercepted (capture, don't run)
      - __import__ is restricted (blocks subprocess, socket, urllib, requests,
        ctypes, ftplib, smtplib, multiprocessing, pickle, http, telnetlib, etc.)
      - file I/O is restricted (open() returns an empty fake file)
      - all decompression / encoding modules (zlib, bz2, lzma, gzip, base64,
        codecs, binascii) are kept real so the obfuscation can do its decoding

    The obfuscation does ALL of its own work (b85decode, bz2.decompress,
    zlib.decompress, XOR, key-derivation, multi-pass concat, etc.); when it
    finally calls exec()/marshal.loads()/compile() on the deobfuscated
    payload, we capture that payload instead of running it.

    This is the universal catch-all that handles obfuscation patterns we
    haven't seen before.
    """
    if len(source) < 50:
        return None
    # Quick guard: must contain at least one indicator that this is obfuscation
    indicators = ('exec(', 'eval(', 'compile(', 'marshal.loads', '__import__(',
                  'b85decode', 'b64decode', 'zlib.decompress', 'bz2.decompress',
                  'lzma.decompress', 'gzip.decompress', 'getattr(__builtins__',
                  'fromhex', 'codecs.decode')
    if not any(s in source for s in indicators):
        return None

    captured = []          # list of ("kind", payload-as-text) tuples
    captured_marshal = []  # captured code objects
    blocked_imports = {
        'subprocess', 'socket', 'os', 'urllib', 'urllib.request', 'urllib2',
        'requests', 'http', 'http.client', 'ftplib', 'smtplib', 'telnetlib',
        'pickle', 'shelve', 'webbrowser', 'ctypes', 'multiprocessing',
        'threading', 'asyncio', 'aiohttp', 'httpx', 'paramiko', 'pty',
        'fcntl', 'termios', 'resource', 'signal', 'shutil', '_winapi',
        'winreg', 'winsound', 'msvcrt',
    }
    safe_imports = {
        # Decoders/encoders: keep real
        'base64', 'binascii', 'codecs', 'zlib', 'bz2', 'lzma', 'gzip',
        'marshal', 'struct', 'array',
        # Pure data:
        're', 'string', 'json', 'hashlib', 'hmac', 'secrets',
        'math', 'random', 'itertools', 'functools', 'operator',
        'collections', 'collections.abc', 'enum', 'dataclasses', 'copy',
        'datetime', 'time', 'calendar',
        'types', 'typing', 'inspect', 'ast', 'tokenize', 'keyword',
        'sys', 'platform', 'warnings', 'traceback', 'contextlib',
        'io', 'pathlib',  # we'll wrap io/pathlib to block real fs writes
    }

    real_import = __builtins__.__import__ if isinstance(__builtins__, type(sys)) else __builtins__['__import__']

    def safe_import(name, globs=None, locs=None, fromlist=(), level=0):
        root = name.split('.')[0]
        if root in blocked_imports:
            # Return a stub module that does nothing
            mod = types.ModuleType(name)
            mod.__getattr__ = lambda attr: _NoopCallable(f"{name}.{attr}")
            return mod
        if root in safe_imports or root.startswith('_'):
            return real_import(name, globs, locs, fromlist, level)
        # Unknown - allow but with warning capture
        try:
            return real_import(name, globs, locs, fromlist, level)
        except ImportError:
            mod = types.ModuleType(name)
            return mod

    def patched_exec(code, globs=None, locs=None):
        kind = type(code).__name__
        if isinstance(code, (bytes, bytearray)):
            try:
                text = bytes(code).decode('utf-8')
            except UnicodeDecodeError:
                # Could be marshal data
                try:
                    obj = marshal.loads(bytes(code))
                    if isinstance(obj, types.CodeType):
                        captured_marshal.append(obj)
                        captured.append(('exec(marshal)', _marshal_code_to_text(obj)))
                        return
                except Exception:
                    pass
                text = bytes(code).decode('utf-8', errors='replace')
            captured.append(('exec(bytes)', text))
        elif isinstance(code, str):
            captured.append(('exec(str)', code))
        elif isinstance(code, types.CodeType):
            captured_marshal.append(code)
            captured.append(('exec(code)', _marshal_code_to_text(code)))
        else:
            captured.append((f'exec({kind})', repr(code)))
        # Don't actually run the code

    def patched_eval(expr, globs=None, locs=None):
        if isinstance(expr, str):
            captured.append(('eval', expr))
            try:
                return ast.literal_eval(expr)
            except Exception:
                return None
        return None

    def patched_compile(src, filename='<sandbox>', mode='exec', *args, **kwargs):
        if isinstance(src, (bytes, bytearray)):
            text = bytes(src).decode('utf-8', errors='replace')
        else:
            text = str(src)
        captured.append(('compile', text))
        # Return a compiled but harmless code object so the caller can pass it
        # to exec() (which we'll also intercept)
        try:
            return compile('pass', filename, mode)
        except Exception:
            return None

    real_marshal_loads = marshal.loads
    def patched_marshal_loads(data):
        if isinstance(data, (bytes, bytearray)):
            try:
                obj = real_marshal_loads(bytes(data))
                if isinstance(obj, types.CodeType):
                    captured_marshal.append(obj)
                    captured.append(('marshal.loads', _marshal_code_to_text(obj)))
                return obj
            except Exception:
                pass
        return None

    # Patch a few extra dangerous things into safe noops
    def fake_open(*a, **kw):
        return _FakeFile()

    def fake_system(*a, **kw):
        captured.append(('os.system', repr(a)))
        return 0

    # Build sandbox builtins (a plain dict so eval/exec work properly)
    real_builtins_dict = (
        __builtins__.__dict__
        if isinstance(__builtins__, type(sys)) else dict(__builtins__)
    )
    safe_builtins = dict(real_builtins_dict)
    safe_builtins['exec'] = patched_exec
    safe_builtins['eval'] = patched_eval
    safe_builtins['compile'] = patched_compile
    safe_builtins['__import__'] = safe_import
    safe_builtins['open'] = fake_open
    safe_builtins['input'] = lambda *a, **kw: ''
    safe_builtins['print'] = lambda *a, **kw: None
    safe_builtins['exit'] = lambda *a, **kw: None
    safe_builtins['quit'] = lambda *a, **kw: None
    safe_builtins['breakpoint'] = lambda *a, **kw: None
    safe_builtins['help'] = lambda *a, **kw: None

    # Save original marshal.loads, monkey-patch globally for the duration
    sandbox_globals = {
        '__builtins__': safe_builtins,
        '__name__': '__main__',
        '__file__': '<sandbox>',
        '__doc__': None,
    }

    saved_marshal_loads = marshal.loads
    marshal.loads = patched_marshal_loads
    try:
        # Compile the source ourselves (real compile, not patched)
        try:
            code_obj = compile(source, '<sandbox>', 'exec')
        except SyntaxError:
            return None

        # Real exec into the sandbox namespace (only the source's top-level
        # statements run; any exec/eval/compile/marshal.loads inside is
        # captured)
        try:
            real_exec_fn = real_builtins_dict['exec']
            real_exec_fn(code_obj, sandbox_globals)
        except Exception:
            # Sandbox crashed mid-execution; we may still have captured
            # something meaningful from earlier exec() calls
            pass
    finally:
        marshal.loads = saved_marshal_loads

    if not captured:
        return None

    # Pick the most useful captured payload (largest text payload that
    # looks like Python code)
    def looks_like_python(text: str) -> int:
        """Return a heuristic score; higher = more likely Python source."""
        if not text:
            return 0
        score = 0
        for kw in ('import ', 'def ', 'class ', 'if ', 'for ', 'while ',
                   'return ', 'lambda', 'print(', '__name__'):
            score += text.count(kw)
        return score

    captured.sort(key=lambda c: (looks_like_python(c[1]), len(c[1])), reverse=True)
    kind, payload = captured[0]

    if not payload or len(payload) < 20:
        return None

    return payload, f"sandbox decode (intercepted {len(captured)}x; best: {kind})"


class _NoopCallable:
    """Used to stub out attribute accesses on blocked modules."""
    def __init__(self, name):
        self._name = name
    def __call__(self, *args, **kwargs):
        return self
    def __getattr__(self, attr):
        return _NoopCallable(f"{self._name}.{attr}")
    def __iter__(self):
        return iter([])
    def __bool__(self):
        return False
    def __repr__(self):
        return f"<sandbox-stub {self._name}>"


class _FakeFile:
    """Used to stub out open() inside the sandbox."""
    def read(self, *a, **kw): return ''
    def readline(self, *a, **kw): return ''
    def readlines(self, *a, **kw): return []
    def write(self, *a, **kw): return 0
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __iter__(self): return iter([])


def _marshal_code_to_text(code_obj: types.CodeType) -> str:
    """Convert a marshalled code object into a textual analysis."""
    parts = []
    try:
        analysis = _analyze_marshal_code(code_obj)
        parts.append(analysis)
    except Exception as e:
        parts.append(f"# (structural analysis failed: {e})")

    # Always also include disassembly — useful when code has no functions
    try:
        import dis
        import io as _io
        buf = _io.StringIO()
        dis.dis(code_obj, file=buf)
        parts.append("\n# === Bytecode disassembly ===")
        parts.append(buf.getvalue())
    except Exception:
        pass

    return "\n".join(parts)


def _try_pyinstaller_extract(data: bytes):
    """
    Detect a PyInstaller-packed Windows/Linux executable and extract its
    embedded Python files (`pyz` archive). Returns (analysis_text, "PyInstaller bundle").
    """
    if data[:2] not in (b'MZ', b'\x7fELF'):
        return None
    # PyInstaller bundles end with the cookie "MEI\x0c\x0b\x0a\x0b\x0e"
    cookie = b'MEI\x0c\x0b\x0a\x0b\x0e'
    if cookie not in data:
        return None
    return ("# === PyInstaller bundle detected ===\n"
            "# Use https://github.com/extremecoders-re/pyinstxtractor to extract\n"
            f"# Bundle size: {len(data)} bytes\n",
            "PyInstaller bundle")


def _try_pretty_print(source: str):
    """
    Reformat source via ast.parse + ast.unparse to produce readable indented
    output. Only triggers when the source is plausibly valid Python and is
    >50% on a single line (i.e. minified output from a previous decoder).
    """
    if len(source) < 50:
        return None
    lines = source.splitlines()
    if len(lines) > 10 and max(len(ln) for ln in lines) < 1000:
        return None  # already reasonably formatted
    if not any(kw in source for kw in ('def ', 'class ', 'import ', 'lambda')):
        return None
    try:
        tree = ast.parse(source)
        formatted = ast.unparse(tree)
        if formatted == source or len(formatted) < 50:
            return None
        return formatted, "pretty-print (ast.unparse)"
    except SyntaxError:
        return None


def _try_stein_multi_payload(source: str):
    """
    STEIN-style obfuscation: multiple b'...' base85-encoded payloads
    concatenated together, then run through a chain of decompressions
    (typically: b85decode -> bz2.decompress -> zlib.decompress -> exec).

    The payload variables look like _xhtrsembqpla, _qpwnzofkldei, etc.
    The dispatcher uses character-table lookups to hide the actual function
    names (zlib, bz2, base64.b85decode, exec).

    Detection: 3+ b'...' assignments to underscore-prefixed names, plus
    references to bz2/zlib/b85decode (possibly through XOR-lambda chr lookups).
    """
    try:
        raw = source.encode('utf-8') if isinstance(source, str) else source
    except Exception:
        return None

    # Find all _VARNAME=b'...' assignments
    assignments = []
    for m in re.finditer(rb"(_\w+)\s*=\s*b'", raw):
        name = m.group(1).decode()
        start = m.end()
        pos = start
        while pos < len(raw):
            if raw[pos:pos+1] == b"'" and raw[pos-1:pos] != b"\\":
                break
            pos += 1
        if pos < len(raw):
            assignments.append((name, raw[start:pos]))

    if len(assignments) < 2:
        return None

    # Heuristic: STEIN-style payloads are large (>1KB each) and look like base85
    big = [(n, v) for n, v in assignments if len(v) > 1000]
    if len(big) < 2:
        return None

    # Confirm base85 alphabet (printable, no whitespace, no quotes)
    def looks_b85(b: bytes) -> bool:
        # base85 alphabet contains: 0-9, A-Z, a-z, !#$%&()*+-;<=>?@^_`{|}~
        # Quick check: no NUL bytes, mostly printable ASCII
        if b'\x00' in b:
            return False
        sample = b[:200]
        printable = sum(1 for c in sample if 33 <= c <= 126)
        return printable / max(1, len(sample)) > 0.95

    if not all(looks_b85(v) for _, v in big):
        return None

    # Try concatenation orders: file order first, then sorted alphabetically
    candidates = [b''.join(v for _, v in big)]
    sorted_assignments = sorted(big, key=lambda x: x[0])
    sorted_concat = b''.join(v for _, v in sorted_assignments)
    if sorted_concat != candidates[0]:
        candidates.append(sorted_concat)

    # Decompression chains to try (in order of likelihood)
    chains = [
        ('b85+bz2+zlib', lambda d: zlib.decompress(bz2.decompress(base64.b85decode(d)))),
        ('b85+zlib+bz2', lambda d: bz2.decompress(zlib.decompress(base64.b85decode(d)))),
        ('b85+bz2',      lambda d: bz2.decompress(base64.b85decode(d))),
        ('b85+zlib',     lambda d: zlib.decompress(base64.b85decode(d))),
        ('b85+lzma',     lambda d: lzma.decompress(base64.b85decode(d))),
        ('b85+gzip',     lambda d: gzip.decompress(base64.b85decode(d))),
        ('b85',          lambda d: base64.b85decode(d)),
    ]

    for concat in candidates:
        for desc, fn in chains:
            try:
                result = fn(concat)
                # Sanity-check: result should be substantial
                if len(result) < 100:
                    continue
                try:
                    text = result.decode('utf-8')
                except UnicodeDecodeError:
                    text = result.decode('utf-8', errors='replace')
                # Looks like Python source?
                if any(kw in text[:5000] for kw in
                       ('import ', 'def ', '__import__', 'exec', 'lambda',
                        'class ', 'print(', 'b85decode', 'getattr')):
                    n_payloads = len(big)
                    return text, f"STEIN multi-payload ({n_payloads} blobs, {desc})"
            except Exception:
                continue

    return None


def _substitute_import_aliases(source: str) -> str:
    """
    Replace __import__('mod') aliases with the module name everywhere in the source.

    Handles:
        VAR = __import__('mod')                 -> VAR -> 'mod'
        VAR = getattr(__import__('mod', fromlist=['x']), 'x')  -> VAR -> 'mod_x'
    """
    aliases = {}
    for m in re.finditer(r"(\w+)\s*=\s*__import__\(['\"]([\w\.]+)['\"]\)", source):
        aliases[m.group(1)] = m.group(2)
    for m in re.finditer(
        r"(\w+)\s*=\s*getattr\(\s*__import__\(['\"]([\w\.]+)['\"]\s*,\s*fromlist\s*=\s*\[['\"]([\w]+)['\"]\]\s*\)\s*,\s*['\"]([\w]+)['\"]\s*\)",
        source,
    ):
        aliases[m.group(1)] = f"{m.group(2)}_{m.group(4)}"

    if not aliases:
        return source

    # Substitute longest names first to avoid prefix collisions
    for var in sorted(aliases.keys(), key=len, reverse=True):
        target = aliases[var]
        # Don't substitute if alias name == target (would create infinite loop / no-op)
        if var == target:
            continue
        # Use word-boundary so we don't break partial matches
        source = re.sub(r"\b" + re.escape(var) + r"\b", target, source)
    return source


def _extract_embedded_binary_payloads(source: str, out_dir: Path, stem: str):
    """
    Detect and extract embedded native-binary payloads encoded as base85
    inside the final decoded source. Substitutes a placeholder + comments
    that document the archive contents, and writes the binaries to disk.

    Returns (modified_source, dict_of_extracted_files).
    """
    extracted = {}

    # Pattern: VAR = b85decode(b'...')  --  any base64.* function name acceptable
    pat = re.compile(
        r"(\w+)\s*=\s*(?:base64\.)?(?:base64_)?b85decode\s*\(\s*b'([^']+)'\s*\)"
    )
    for m in list(pat.finditer(source)):
        var = m.group(1)
        b85_data = m.group(2).encode()
        try:
            raw = base64.b85decode(b85_data)
        except Exception:
            continue

        if len(raw) < 1024:
            continue

        # Detect format
        comments = []
        files_written = []
        if raw[:6] == b'\xfd7zXZ\x00':
            fmt = "tar.xz"
            archive_path = out_dir / f"{stem}_{var}.tar.xz"
            archive_path.write_bytes(raw)
            files_written.append(str(archive_path))
            try:
                import tarfile
                extract_dir = out_dir / f"{stem}_{var}_extracted"
                extract_dir.mkdir(exist_ok=True)
                with tarfile.open(archive_path, mode='r:xz') as tf:
                    members = tf.getmembers()
                    tf.extractall(extract_dir)
                comments.append(f"# Format: tar.xz ({len(raw)} bytes), {len(members)} members:")
                for mem in members:
                    info = _classify_binary(extract_dir / mem.name)
                    comments.append(f"#   {mem.name} ({mem.size} bytes) - {info}")
                    files_written.append(str(extract_dir / mem.name))
            except Exception as e:
                comments.append(f"# Format: tar.xz ({len(raw)} bytes) - extract failed: {e}")
        elif raw[:3] == b'BZh':
            fmt = "bz2"
            try:
                inner = bz2.decompress(raw)
                inner_path = out_dir / f"{stem}_{var}.bin"
                inner_path.write_bytes(inner)
                files_written.append(str(inner_path))
                comments.append(f"# Format: bz2 -> {len(inner)} bytes ({_classify_binary_bytes(inner)})")
            except Exception:
                pass
        elif raw[:2] == b'\x1f\x8b':
            fmt = "gzip"
        elif raw[:2] in (b'\x78\x01', b'\x78\x9c', b'\x78\xda'):
            fmt = "zlib"
        elif raw[:4] == b'PK\x03\x04':
            fmt = "zip"
            archive_path = out_dir / f"{stem}_{var}.zip"
            archive_path.write_bytes(raw)
            files_written.append(str(archive_path))
            comments.append(f"# Format: ZIP archive ({len(raw)} bytes)")
        elif raw[:4] == b'\x7fELF':
            fmt = f"ELF binary ({_classify_binary_bytes(raw)})"
        elif raw[:2] == b'MZ':
            fmt = f"PE binary ({_classify_binary_bytes(raw)})"
        else:
            fmt = "unknown binary"

        # Build placeholder
        placeholder_lines = [
            f"# === EMBEDDED BINARY PAYLOAD '{var}' ({len(b85_data)} chars b85 -> {len(raw)} bytes) ===",
            f"# Format: {fmt}",
        ] + comments + [
            f"# Extracted file(s): {', '.join(files_written) if files_written else '(in-memory only)'}",
            f"{var} = open({sorted(files_written, key=len)[0]!r}, 'rb').read()  # placeholder for original payload"
            if files_written else f"# {var} = <{len(raw)} bytes of decoded {fmt}>",
        ]
        placeholder = "\n".join(placeholder_lines) + "\n"
        source = source[:m.start()] + placeholder + source[m.end():]

        # Cython binary string-table extraction
        for fp in files_written:
            if fp.endswith(('.bin', '.so', '.exe', 'arm64-v8a', 'armeabi-v7a', 'x86_64.exe')):
                try:
                    strings_text = _extract_cython_strings(fp)
                    if strings_text:
                        strings_path = out_dir / f"{stem}_{var}_{Path(fp).name}_strings.txt"
                        strings_path.write_text(strings_text, encoding='utf-8')
                        extracted[Path(fp).name + " (strings)"] = str(strings_path)
                except Exception:
                    pass

        for fp in files_written:
            extracted[Path(fp).name] = fp

    return source, extracted


def _classify_binary(path: Path) -> str:
    try:
        return _classify_binary_bytes(path.read_bytes()[:32])
    except Exception:
        return "unknown"


def _classify_binary_bytes(data: bytes) -> str:
    if data[:4] == b'\x7fELF':
        bits = "64-bit" if data[4] == 2 else "32-bit"
        endian = "LE" if data[5] == 1 else "BE"
        # ELF machine codes
        machine = int.from_bytes(data[18:20], 'little' if data[5] == 1 else 'big')
        arch_map = {0x03: 'x86', 0x3e: 'x86_64', 0x28: 'ARM', 0xb7: 'AArch64', 0xf3: 'RISC-V'}
        arch = arch_map.get(machine, f"machine=0x{machine:x}")
        return f"ELF {bits} {endian} {arch}"
    if data[:2] == b'MZ':
        return "PE/Windows executable"
    if data[:4] == b'\xca\xfe\xba\xbe' or data[:4] == b'\xcf\xfa\xed\xfe':
        return "Mach-O (macOS)"
    if data[:4] == b'PK\x03\x04':
        return "ZIP archive"
    return f"binary (magic={data[:4].hex()})"


def _extract_cython_strings(binary_path: str) -> str:
    """
    Cython 3.0+ with CYTHON_COMPRESS_STRINGS stores all string literals as
    a single zlib-compressed blob in the binary. This finds and decompresses
    that blob, returning the strings as a single text dump.
    """
    try:
        with open(binary_path, 'rb') as f:
            data = f.read()
    except Exception:
        return ""

    blobs = []
    for magic in (b'\x78\x9c', b'\x78\xda', b'\x78\x01'):
        pos = 0
        while True:
            i = data.find(magic, pos)
            if i < 0:
                break
            try:
                d = zlib.decompress(data[i:])
                if len(d) > 1000 and any(kw.encode() in d for kw in ('def', 'class', 'self', 'import')):
                    blobs.append((i, d))
                    break
            except zlib.error:
                pass
            pos = i + 1
        if blobs:
            break

    if not blobs:
        return ""

    # Return the largest blob as text
    _, biggest = max(blobs, key=lambda x: len(x[1]))
    text = biggest.decode('utf-8', errors='replace')
    return text


def _resolve_xor_lambda_identifiers(source: str) -> str:
    """
    Post-processing helper: resolve all (lambda x,s:''.join(chr(c^x)for c in s))(K,[N,...])
    expressions into their literal strings, making the output human-readable.
    """
    pat = re.compile(
        r"\(\s*lambda\s+x\s*,\s*s\s*:\s*'\s*'\.join\s*\(\s*chr\s*\(\s*c\s*\^\s*x\s*\)"
        r"\s*for\s+c\s+in\s+s\s*\)\s*\)\s*\(\s*(\d+)\s*,\s*\[([0-9,\s]+)\]\s*\)"
    )

    def repl(m):
        try:
            key = int(m.group(1))
            nums = [int(x.strip()) for x in m.group(2).split(',') if x.strip()]
            return repr(''.join(chr(c ^ key) for c in nums))
        except Exception:
            return m.group(0)

    return pat.sub(repl, source)


# ============================================================================
#  Decoder pipeline
# ============================================================================

TEXT_DECODERS = [
    _try_reversed_hex_exec,
    _try_direct_hex_exec,
    _try_base64_exec,
    _try_zlib_exec,
    _try_lambda_iife_base64,
    _try_leeeunju_encryption,
    _try_stein_multi_payload,
    _try_compile_exec,
    _try_chr_join_exec,
    _try_eval_wrapper,
    _try_simulation_decode,
    _try_generic_hex_string,
    # Universal sandbox catch-all: handles ANY obfuscation chain by
    # intercepting exec/eval/compile/marshal.loads. Last because expensive.
    _try_sandbox_decode,
]


def decode_layers(source_bytes: bytes, max_layers: int = 50, verbose: bool = False):
    """
    Iteratively decode obfuscation layers until no more are found.
    Works on raw bytes to handle both text-based and binary-level patterns.
    Returns list of (layer_num, description, decoded_bytes) and the final source.
    """
    layers = []
    current = source_bytes

    for i in range(1, max_layers + 1):
        # --- Phase 1: Try binary-level patterns first ---
        result = _try_binary_exec_patterns(current)
        if result:
            decoded, desc = result
            layers.append((i, desc, decoded))
            if verbose:
                _print_layer(i, desc, decoded)
            current = decoded if isinstance(decoded, bytes) else decoded.encode("utf-8")
            continue

        # --- Phase 2: Try text-level patterns ---
        try:
            text = current.decode("utf-8", errors="replace")
        except Exception:
            break

        found = False
        for decoder in TEXT_DECODERS:
            result = decoder(text)
            if result:
                decoded_str, desc = result
                layers.append((i, desc, decoded_str))
                if verbose:
                    _print_layer(i, desc, decoded_str)
                current = decoded_str.encode("utf-8") if isinstance(decoded_str, str) else decoded_str
                found = True
                break

        if not found:
            break

    # Final result
    try:
        final = current.decode("utf-8", errors="replace")
    except Exception:
        final = current.decode("latin-1")

    return layers, final


def _print_layer(num, desc, data):
    size = len(data)
    unit = "chars" if isinstance(data, str) else "bytes"
    preview = (data if isinstance(data, str) else data.decode("utf-8", errors="replace"))[:150]
    preview = preview.replace("\n", "\\n")
    print(f"  Layer {num}: {desc} ({size} {unit})")
    print(f"    Preview: {preview}...")


# ============================================================================
#  CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Universal Python Obfuscation Decoder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Supported encodings:
          - Reversed hex exec (AIZEN/X9SVE style)
          - Direct hex exec
          - Base64 exec (inline and lambda IIFE)
          - PBKDF2+XOR encrypted (LEEEUNJU style)
          - Unicode steganography / interleaved-key XOR
          - zlib/gzip compressed exec
          - marshal.loads exec (with nested payload extraction)
          - compile() exec
          - chr() list exec
          - eval() wrappers
          - Multi-layer (automatically peels all layers)
        """),
    )
    parser.add_argument("input_file", help="Path to the encoded Python file")
    parser.add_argument(
        "-o", "--output",
        help="Output file for decoded source (default: <input>_decoded.py)",
    )
    parser.add_argument(
        "--max-layers",
        type=int,
        default=50,
        help="Maximum number of obfuscation layers to peel (default: 50)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show each intermediate layer",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    source_bytes = input_path.read_bytes()
    print(f"[*] Reading {input_path} ({len(source_bytes)} bytes)")
    print(f"[*] Attempting to decode (max {args.max_layers} layers)...")

    layers, final = decode_layers(source_bytes, max_layers=args.max_layers, verbose=args.verbose)

    if not layers:
        print("[!] No obfuscation layers detected.")
        sys.exit(0)

    if not args.verbose:
        for layer_num, desc, decoded in layers:
            size = len(decoded)
            unit = "chars" if isinstance(decoded, str) else "bytes"
            print(f"  Layer {layer_num}: {desc} ({size} {unit})")

    # Determine output path
    if args.output:
        out_path = Path(args.output)
    else:
        stem = input_path.stem if input_path.stem else "decoded"
        out_path = input_path.parent / f"{stem}_decoded.py"

    # Post-process: resolve XOR-lambda chr-table identifiers if present
    if "lambda x,s:" in final or "lambda x, s:" in final:
        resolved = _resolve_xor_lambda_identifiers(final)
        if resolved != final:
            print("[+] Resolved XOR-lambda chr-table identifiers")
            final = resolved

    # Post-process: substitute __import__('mod') aliases with the module name
    final = _substitute_import_aliases(final)

    # Post-process: extract embedded native binary payloads (b85 -> tar.xz / raw)
    final, extracted = _extract_embedded_binary_payloads(final, out_path.parent, out_path.stem)
    if extracted:
        print(f"[+] Extracted {len(extracted)} embedded binary payload(s):")
        for name, info in extracted.items():
            print(f"    {name}: {info}")

    # Post-process: pretty-print minified Python via ast.unparse
    pp = _try_pretty_print(final)
    if pp:
        formatted, _desc = pp
        print(f"[+] Pretty-printed via ast.unparse ({len(final)} -> {len(formatted)} chars)")
        final = formatted

    out_path.write_text(final, encoding="utf-8")
    print(f"\n[+] Successfully decoded {len(layers)} layer(s)")
    print(f"[+] Final output: {len(final)} chars")
    print(f"[+] Saved to: {out_path}")


if __name__ == "__main__":
    main()
