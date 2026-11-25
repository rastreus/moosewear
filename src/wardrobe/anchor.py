"""The canonical self anchor — the anti-drift mechanism.

The daily ritual restyles the wearer's avatar once per scheduled
step (morning fit, three layer checks, pajamas). Each restyle is a
generative edit, and an edit made on top of yesterday's render
inherits that render's small mutations: chained over weeks, the
wearer's face, proportions, and coloring wander until the render
no longer matches the wearer. That is exactly what happened in the
2026-11-25 drift incident (the named regression case in
tests/test_anchor.py).

The anchor is the fix, and it has three parts:

  1. A pinned base image (anchor/moose-canonical.jpg) plus a
     manifest (anchor/anchor.json) carrying its SHA-256 and the
     canonical identity spec. `verify` proves the pinned image is
     bit-identical to the manifest; the pin can never move silently.
  2. A reset-then-dress protocol: every dress first resets the
     avatar to the canonical base, then applies exactly ONE edit.
     Every published render is therefore a single generation from
     the base — chaining, and with it compounding drift, is
     structurally impossible.
  3. One deterministic dress-prompt composer. The identity clause
     of every dress instruction comes from the manifest's spec,
     never from prose retyped into a schedule, so the words that
     pin the identity cannot drift either.

Like core.py, the logic here is pure functions of the manifest and
the files under the anchor directory; the CLI does the printing.
"""

import hashlib
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANCHOR_DIR = PROJECT_ROOT / "anchor"
MANIFEST_NAME = "anchor.json"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AnchorError(Exception):
    """The anchor manifest cannot be loaded at all."""


def load_manifest(anchor_dir):
    """The manifest dict from an anchor directory.

    Raises AnchorError when the manifest is missing, is not valid
    JSON, or is not a JSON object.
    """
    path = Path(anchor_dir) / MANIFEST_NAME
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AnchorError(f"cannot read anchor manifest {path}: {exc}")
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnchorError(f"anchor manifest {path} is not valid JSON: {exc}")
    if not isinstance(manifest, dict):
        raise AnchorError(f"anchor manifest {path} is not a JSON object")
    return manifest


def validate_manifest(manifest):
    """Problems with a manifest dict; empty means it is well-formed."""
    problems = []
    image = manifest.get("image")
    if not isinstance(image, str) or not image.strip():
        problems.append("manifest 'image' must be a non-empty file name")
    elif Path(image).name != image:
        problems.append("manifest 'image' must be a bare file name, "
                        "not a path")
    sha = manifest.get("sha256")
    if not isinstance(sha, str) or not _SHA256_RE.match(sha):
        problems.append("manifest 'sha256' must be 64 lowercase hex "
                        "characters")
    spec = manifest.get("identity_spec")
    if not isinstance(spec, str) or not spec.strip():
        problems.append("manifest 'identity_spec' must be non-empty text")
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("manifest 'name' must be non-empty text")
    return problems


def file_sha256(path):
    """The SHA-256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(anchor_dir):
    """Problems with the anchor at a directory; empty means anchored.

    The anchor holds when the manifest is well-formed, the pinned
    image exists beside it, and the image's bytes hash to the
    manifest's pin.
    """
    anchor_dir = Path(anchor_dir)
    try:
        manifest = load_manifest(anchor_dir)
    except AnchorError as exc:
        return [str(exc)]
    problems = validate_manifest(manifest)
    if problems:
        return problems
    image_path = anchor_dir / manifest["image"]
    if not image_path.is_file():
        return [f"anchor image missing: {image_path}"]
    actual = file_sha256(image_path)
    if actual != manifest["sha256"]:
        problems.append(
            f"anchor image hash mismatch: manifest pins "
            f"{manifest['sha256']}, the file on disk hashes to "
            f"{actual} — the canonical base has moved; restore it "
            f"from the manifest's source before dressing again")
    return problems


def dress_prompt(manifest, outfit, context=""):
    """The one canonical dress instruction for an outfit.

    Deterministic: the same manifest, outfit, and context always
    compose the same text, and the identity clause is always the
    manifest's spec verbatim — the wearer himself never changes,
    only the clothing does.
    """
    name = manifest["name"]
    parts = [f"Dress {name} in {outfit}."]
    if context and context.strip():
        parts.append(context.strip().rstrip(".") + ".")
    parts.append(
        f"{name} himself stays exactly the same — "
        f"{manifest['identity_spec']} — only the clothing is new.")
    parts.append("Soft, warm, storybook style.")
    return " ".join(parts)
