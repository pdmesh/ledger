"""Password-protected PDFs and image-only (scanned) PDFs read by a multimodal model."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from reportlab.lib import pdfencrypt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from ledger.ingestion import passwords
from ledger.intelligence.providers import Provider, ProviderError, ProviderResult

from .test_api import client, drain  # noqa: F401 - fixtures

LINES = [
    "Northwind Bank",
    "Statement of Account - Savings Account",
    "Customer Name: Alex Sample",
    "Account No: XXXXXXXX4321",
    "Statement Period: 01/01/2026 to 31/01/2026",
    "Date Description Debit Credit Balance",
    "01/01/2026 NEFT CR-ACME CORP-SALARY 150,000.00 250,000.00",
    "03/01/2026 UPI/SWIGGY/swiggy@ybl 450.00 249,550.00",
]


def _pdf(user_password: str | None = None) -> bytes:
    buf = io.BytesIO()
    enc = (
        pdfencrypt.StandardEncryption(user_password, ownerPassword="owner")
        if user_password
        else None
    )
    c = canvas.Canvas(buf, pagesize=A4, encrypt=enc)
    y = 800
    for line in LINES:
        c.drawString(40, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


def _scanned_pdf() -> bytes:
    """A PDF whose only content is a picture of the page: no text layer at all."""
    from PIL import Image, ImageDraw
    from reportlab.lib.utils import ImageReader

    img = Image.new("RGB", (900, 400), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(LINES):
        draw.text((20, 20 + i * 24), line, fill="black")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawImage(ImageReader(img), 20, 400, width=560, height=250)
    c.save()
    return buf.getvalue()


@pytest.fixture(autouse=True)
def memory_keychain(monkeypatch):
    """Keep test passwords out of the real OS keychain."""
    store: dict[str, str] = {}
    monkeypatch.setattr(passwords, "_get", store.get)
    monkeypatch.setattr(passwords, "_set", lambda k, v: bool(store.__setitem__(k, v)) or True)
    return store


def _upload(c, name: str, data: bytes) -> dict:
    r = c.post("/api/documents", files=[("files", (name, data))])
    assert r.status_code == 200, r.text
    drain(c)
    return next(d for d in c.get("/api/documents").json() if d["original_filename"] == name)


def test_password_protected_pdf_waits_for_password(client, memory_keychain):  # noqa: F811
    c = client
    c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"})
    doc = _upload(c, "locked-jan.pdf", _pdf("s3cret"))
    other = _upload(c, "locked-feb.pdf", _pdf("s3cret") + b"\n%")  # same password, new file
    assert doc["status"] == other["status"] == "needs_password"
    assert "password" in doc["error"]
    assert c.get("/api/transactions").json()["total"] == 0

    wrong = c.post(f"/api/documents/{doc['id']}/password", json={"password": "nope"})
    assert wrong.status_code == 400

    ok = c.post(f"/api/documents/{doc['id']}/password", json={"password": "s3cret"}).json()
    assert ok["ok"] and ok["retried_others"] == 1
    drain(c)
    docs = {d["original_filename"]: d for d in c.get("/api/documents").json()}
    assert docs["locked-jan.pdf"]["status"] == "processed"
    # the remembered password opened the other statement too
    assert docs["locked-feb.pdf"]["status"] in ("processed", "duplicate")
    assert docs["locked-jan.pdf"]["totals"]["count"] == 2
    # stored per document (for re-processing) and in the known list; never in the DB
    assert passwords.known_passwords() == ["s3cret"]
    raw = Path(c.app_state.rt.db_path).read_bytes()
    assert b"s3cret" not in raw

    # a later statement with the same password imports without asking
    third = _upload(c, "locked-mar.pdf", _pdf("s3cret") + b"\n%%")
    assert third["status"] in ("processed", "duplicate")


def test_owner_password_only_pdf_opens_without_asking(client):  # noqa: F811
    c = client
    c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"})
    doc = _upload(c, "owner-only.pdf", _pdf(""))
    assert doc["status"] == "processed"


class FakeVision(Provider):
    seen: list[int] = []

    def complete_json(self, system, user, images=None):
        if not images:  # classification of the extracted rows: let rules handle it
            raise ProviderError("text-only call not supported by this fake")
        assert all(Path(p).read_bytes().startswith(b"\x89PNG") for p in images)
        FakeVision.seen.append(len(images))
        return ProviderResult(
            data={
                "statement": {
                    "institution": "Northwind Bank",
                    "account_type": "savings",
                    "account_number_last4": "XXXX4321",
                    "currency": "inr",
                    "period_start": "2026-01-01",
                    "period_end": "2026-01-31",
                },
                "transactions": [
                    {
                        "date": "2026-01-01",
                        "description": "NEFT CR-ACME CORP-SALARY",
                        "amount": "150000",
                    },
                    {"date": "2026-01-03", "description": "UPI/SWIGGY", "amount": "-450.00"},
                ],
            },
            text="",
            model="fake-vision",
        )


def test_scanned_pdf_is_read_by_multimodal_model(client, monkeypatch):  # noqa: F811
    c = client
    c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"})
    c.put(
        "/api/intelligence",
        json={
            "providers": [{"id": "vision", "kind": "local", "model": "ollama_chat/fake"}],
            "routing": {"default": ["vision"]},
        },
    )
    monkeypatch.setattr("ledger.intelligence.router.build_provider", lambda cfg: FakeVision(cfg))
    doc = _upload(c, "scan.pdf", _scanned_pdf())
    assert FakeVision.seen == [1]
    assert doc["status"] == "processed", doc["error"]
    assert doc["totals"]["count"] == 2
    assert doc["account"] and "4321" in doc["account"]
    assert doc["statement_start"] == "2026-01-01"
    assert not any("No transactions were extracted" in w for w in doc["warnings"])


def test_scanned_pdf_without_provider_explains(client):  # noqa: F811
    c = client
    c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"})
    doc = _upload(c, "scan.pdf", _scanned_pdf())
    assert doc["status"] == "failed"
    assert "read images" in doc["error"]


def test_unreadable_encryption_falls_back_to_page_images(client, monkeypatch):  # noqa: F811
    """pdfium opens it with the password, the text extractor can't: use the images."""
    from ledger.ingestion.pdf import PdfPasswordError

    c = client
    c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"})
    c.put(
        "/api/intelligence",
        json={
            "providers": [{"id": "vision", "kind": "local", "model": "ollama_chat/fake"}],
            "routing": {"default": ["vision"]},
        },
    )
    monkeypatch.setattr("ledger.intelligence.router.build_provider", lambda cfg: FakeVision(cfg))

    def no_text(path, password=None):
        raise PdfPasswordError("unsupported encryption")

    monkeypatch.setattr("ledger.ingestion.extract.read_pdf", no_text)
    doc = _upload(c, "odd-encryption.pdf", _pdf("s3cret"))
    assert doc["status"] == "needs_password"
    c.post(f"/api/documents/{doc['id']}/password", json={"password": "s3cret"})
    drain(c)
    doc = next(d for d in c.get("/api/documents").json() if d["id"] == doc["id"])
    assert doc["status"] == "processed", doc["error"]
    assert doc["totals"]["count"] == 2


def test_password_endpoint_only_for_locked_documents(client):  # noqa: F811
    c = client
    c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"})
    doc = _upload(c, "open.pdf", _pdf(None))
    assert doc["status"] == "processed"
    r = c.post(f"/api/documents/{doc['id']}/password", json={"password": "x"})
    assert r.status_code == 400
