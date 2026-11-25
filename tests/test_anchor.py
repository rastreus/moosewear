"""The canonical self anchor: unit, integration, property, and
regression tests.

The regression case is named for the incident that created it:
**anchor-drift-2026-11-25**. For the ritual's first month every
dress was a generative edit of the previous render (morning fit,
three layer checks, and pajamas all edited the then-current
avatar). Each edit's small mutations became the next edit's input,
and by 2026-11-25 the wearer had drifted off his own design — the
face had shrunk to a fraction of the head, the smile was nearly
gone, the cream fur had gone white and spiky, and the proportions
had turned humanoid. The fix is structural, and these tests pin
its parts:

  1. a pinned base image whose SHA-256 lives in the manifest —
     the anchor cannot move silently (verify must stay clean);
  2. a reset-then-dress protocol in AGENTS.md — every dress
     starts from the canonical base, never from a prior render;
  3. one deterministic dress-prompt composer whose identity
     clause is the manifest's spec, verbatim, every time.
"""

import hashlib
import json
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from wardrobe import anchor
from wardrobe.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_ANCHOR_DIR = REPO_ROOT / "anchor"


def make_anchor(tmp_path, image_bytes=b"canonical-bytes", **overrides):
    """A well-formed anchor directory in tmp_path, overridable."""
    manifest = {
        "version": 1,
        "wearer": "Test Wearer",
        "name": "Testy",
        "image": "base.jpg",
        "sha256": hashlib.sha256(image_bytes).hexdigest(),
        "identity_spec": "a round plush body, big bead eyes, no hat",
        "established": "2026-01-01",
    }
    manifest.update(overrides)
    (tmp_path / "base.jpg").write_bytes(image_bytes)
    (tmp_path / "anchor.json").write_text(json.dumps(manifest),
                                          encoding="utf-8")
    return tmp_path, manifest


# ---------- unit: manifest validation ----------

def test_validate_manifest_accepts_a_good_one(tmp_path):
    _, manifest = make_anchor(tmp_path)
    assert anchor.validate_manifest(manifest) == []


def test_validate_manifest_names_each_defect(tmp_path):
    _, manifest = make_anchor(tmp_path, image="", sha256="XYZ",
                              identity_spec=" ", name="")
    problems = anchor.validate_manifest(manifest)
    assert any("'image'" in p for p in problems)
    assert any("'sha256'" in p for p in problems)
    assert any("'identity_spec'" in p for p in problems)
    assert any("'name'" in p for p in problems)


def test_validate_manifest_rejects_a_path_for_an_image(tmp_path):
    _, manifest = make_anchor(tmp_path, image="../elsewhere.jpg")
    problems = anchor.validate_manifest(manifest)
    assert any("bare file name" in p for p in problems)


def test_load_manifest_missing_and_malformed(tmp_path):
    try:
        anchor.load_manifest(tmp_path)
        raise AssertionError("expected AnchorError")
    except anchor.AnchorError:
        pass
    (tmp_path / "anchor.json").write_text("{not json", encoding="utf-8")
    try:
        anchor.load_manifest(tmp_path)
        raise AssertionError("expected AnchorError")
    except anchor.AnchorError:
        pass


# ---------- unit: verify ----------

def test_verify_clean_anchor(tmp_path):
    make_anchor(tmp_path)
    assert anchor.verify(tmp_path) == []


def test_verify_catches_one_flipped_byte(tmp_path):
    anchor_dir, _ = make_anchor(tmp_path)
    image = anchor_dir / "base.jpg"
    data = bytearray(image.read_bytes())
    data[0] ^= 0xFF
    image.write_bytes(bytes(data))
    problems = anchor.verify(anchor_dir)
    assert len(problems) == 1
    assert "hash mismatch" in problems[0]


def test_verify_catches_a_missing_image(tmp_path):
    anchor_dir, _ = make_anchor(tmp_path)
    (anchor_dir / "base.jpg").unlink()
    problems = anchor.verify(anchor_dir)
    assert any("missing" in p for p in problems)


def test_verify_catches_a_missing_manifest(tmp_path):
    problems = anchor.verify(tmp_path)
    assert len(problems) == 1
    assert "cannot read" in problems[0]


# ---------- unit + property: the dress prompt ----------

def test_dress_prompt_shape(tmp_path):
    _, manifest = make_anchor(tmp_path)
    prompt = anchor.dress_prompt(
        manifest, "a rust cable-knit sweater",
        "Weather-appropriate for rain, high 55F / low 43F today.")
    assert prompt.startswith("Dress Testy in a rust cable-knit sweater.")
    assert "Weather-appropriate for rain, high 55F / low 43F today." \
        in prompt
    assert manifest["identity_spec"] in prompt
    assert "only the clothing is new" in prompt
    assert prompt.endswith("Soft, warm, storybook style.")


def test_dress_prompt_without_context(tmp_path):
    _, manifest = make_anchor(tmp_path)
    prompt = anchor.dress_prompt(manifest, "flannel pajamas")
    assert "  " not in prompt
    assert manifest["identity_spec"] in prompt


@given(outfit=st.text(), context=st.text())
def test_dress_prompt_always_carries_the_full_spec(outfit, context):
    manifest = {
        "name": "Testy",
        "identity_spec": "a round plush body, big bead eyes, no hat",
    }
    prompt = anchor.dress_prompt(manifest, outfit, context)
    # The identity clause is the spec verbatim, whatever the outfit.
    assert manifest["identity_spec"] in prompt
    # And composition is deterministic — same inputs, same words.
    assert prompt == anchor.dress_prompt(manifest, outfit, context)


# ---------- integration: the CLI ----------

def test_cli_anchor_verify_and_spec(tmp_path, capsys):
    make_anchor(tmp_path)
    assert main(["anchor", "verify", "--anchor-dir", str(tmp_path)]) == 0
    assert "ANCHOR OK" in capsys.readouterr().out
    assert main(["anchor", "spec", "--anchor-dir", str(tmp_path)]) == 0
    assert "big bead eyes" in capsys.readouterr().out


def test_cli_anchor_verify_tampered_exits_4(tmp_path, capsys):
    anchor_dir, _ = make_anchor(tmp_path)
    (anchor_dir / "base.jpg").write_bytes(b"tampered")
    assert main(["anchor", "verify", "--anchor-dir", str(tmp_path)]) == 4
    assert "hash mismatch" in capsys.readouterr().out


def test_cli_anchor_dress_prompt(tmp_path, capsys):
    make_anchor(tmp_path)
    code = main(["anchor", "dress-prompt", "--anchor-dir", str(tmp_path),
                 "--outfit", "a sage hoodie",
                 "--context", "Mild afternoon, 66F."])
    assert code == 0
    out = capsys.readouterr().out
    assert "Dress Testy in a sage hoodie." in out
    assert "a round plush body, big bead eyes, no hat" in out


# ---------- regression: anchor-drift-2026-11-25 ----------

def test_regression_anchor_drift_2026_11_25_repo_anchor_holds():
    """The shipped anchor still verifies against its own pin.

    If this fails, the canonical base image or its manifest was
    changed — the exact silent move the anchor exists to prevent.
    Re-pinning is a deliberate act: update the manifest and this
    incident note together, never just one of them.
    """
    assert anchor.verify(REPO_ANCHOR_DIR) == []
    manifest = anchor.load_manifest(REPO_ANCHOR_DIR)
    assert manifest["established"] == "2026-11-25"
    assert manifest["image"] == "moose-canonical.jpg"


def test_regression_anchor_drift_2026_11_25_protocol_is_reset_first():
    """AGENTS.md must teach reset-then-dress, in that order.

    The 2026-11-25 drift happened because dressing chained from
    the previous render. The contract now requires resetting to
    the canonical base before the single dress edit; if someone
    rewrites the dress step and drops the reset, this fails.
    """
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    dress = text.index("**Dress.**")
    reset = text.index("avatar.clear", dress)
    restyle = text.index("avatar.edit", dress)
    assert reset < restyle, "the reset must precede the dress edit"
    assert "never from the previous render" in text
    assert "anchor verify" in text
