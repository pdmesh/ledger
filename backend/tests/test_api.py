from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from ledger.app import create_app
from ledger.jobs import run_pending
from ledger.settings import RuntimeSettings

from .conftest import FIXTURES


@pytest.fixture
def client(tmp_path):
    rt = RuntimeSettings(data_dir=tmp_path / "data", start_worker=False, api_token="t0ken")
    app = create_app(rt)
    with TestClient(app) as c:
        c.headers["Authorization"] = "Bearer t0ken"
        c.app_state = app.state  # type: ignore[attr-defined]
        yield c


def drain(client):
    run_pending(client.app_state.db, client.app_state.rt)


def setup_household(c):
    assert (
        c.post("/api/onboarding", json={"country": "IN", "base_currency": "INR"}).status_code == 200
    )
    a = c.post(
        "/api/identities", json={"display_name": "Alex Sample", "aliases": ["A Sample"]}
    ).json()
    b = c.post("/api/identities", json={"display_name": "Sam Sample"}).json()
    for name in ("Northwind Bank", "Contoso Bank"):
        c.post("/api/institutions", json={"name": name})
    c.post("/api/institutions", json={"name": "Fabrikam Card", "aliases": ["fabrikam"]})
    return a, b


def upload(c, *names):
    files = [("files", (n, (FIXTURES / n).read_bytes())) for n in names]
    r = c.post("/api/documents", files=files)
    assert r.status_code == 200, r.text
    drain(c)
    return r.json()


def test_auth_required(tmp_path):
    rt = RuntimeSettings(data_dir=tmp_path / "d", start_worker=False, api_token="x")
    with TestClient(create_app(rt)) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/settings").status_code == 401
        # tokens in URLs are not accepted (they leak into logs and history)
        assert c.get("/api/settings", params={"token": "x"}).status_code == 401
        assert c.get("/api/settings", headers={"Authorization": "Bearer x"}).status_code == 200


def test_open_original_uses_os_viewer(client, monkeypatch):
    c = client
    setup_household(c)
    upload(c, "northwind_savings_2026-01.csv")
    doc = c.get("/api/documents").json()[0]
    opened = []
    monkeypatch.setattr("ledger.desktop.open_path", lambda p, reveal=False: opened.append(p))
    assert c.post(f"/api/documents/{doc['id']}/open").json() == {"ok": True}
    assert opened and opened[0].suffix == ".csv" and opened[0].exists()
    assert c.post("/api/documents/9999/open").status_code == 404


def test_full_flow(client):
    c = client
    alex, sam = setup_household(c)
    res = upload(
        c,
        "northwind_savings_2026-01.csv",
        "contoso_savings_2026-01.xlsx",
        "fabrikam_card_2026-01.pdf",
    )
    assert [r["status"] for r in res["results"]] == ["queued"] * 3
    # duplicate upload is detected
    again = upload(c, "northwind_savings_2026-01.csv")
    assert again["results"][0]["status"] == "duplicate"

    docs = c.get("/api/documents").json()
    assert {d["status"] for d in docs} == {"processed"}

    ov = c.get("/api/analytics/overview").json()
    assert Decimal(ov["metrics"]["income"]) == Decimal("240250")

    # individual & joint views
    alex_ov = c.get(
        "/api/analytics/overview", params={"identity_id": alex["id"], "scope": "individual"}
    ).json()
    sam_ov = c.get(
        "/api/analytics/overview", params={"identity_id": sam["id"], "scope": "individual"}
    ).json()
    assert Decimal(alex_ov["metrics"]["income"]) == Decimal("150250")
    assert Decimal(sam_ov["metrics"]["income"]) == Decimal("90000")
    hh = c.get("/api/analytics/household").json()
    assert {h["name"] for h in hh} == {"Alex Sample", "Sam Sample", "Joint accounts"}

    # explorer filters
    txns = c.get("/api/transactions", params={"role": "transfer"}).json()
    assert txns["total"] >= 4
    swiggy = c.get("/api/transactions", params={"q": "swiggy"}).json()
    assert swiggy["total"] == 3

    # taxonomy rename propagates by reference (no reprocessing)
    cats = {x["slug"]: x for x in c.get("/api/categories").json()}
    r = c.patch(f"/api/categories/{cats['food']['id']}", json={"name": "Eating out"})
    assert r.json()["propagation"] == "none"

    # merchant mapping propagates to history and future imports
    merchants = c.get("/api/merchants", params={"q": "swiggy"}).json()["items"]
    assert len(merchants) == 1
    r = c.patch(
        f"/api/merchants/{merchants[0]['id']}", json={"default_category_id": cats["food"]["id"]}
    )
    assert r.json()["reclassified"] == 3
    swiggy = c.get("/api/transactions", params={"q": "swiggy"}).json()["items"]
    assert {t["category"] for t in swiggy} == {"Eating out"}
    assert {t["classification_method"] for t in swiggy} == {"merchant_map"}

    # merging categories moves historical transactions
    r = c.post(f"/api/categories/{cats['food']['id']}/merge-into/{cats['groceries']['id']}")
    assert r.json()["moved_transactions"] == 3

    # user override is pinned and survives reclassification
    t = c.get("/api/transactions", params={"q": "STARBUCKS"}).json()["items"][0]
    r = c.post(
        f"/api/transactions/{t['id']}/override",
        json={"field": "category", "value": cats["entertainment"]["id"], "apply_to_similar": True},
    )
    assert r.status_code == 200 and r.json()["learned"]
    c.post(
        "/api/rules",
        json={
            "name": "coffee",
            "conditions": {"description_contains": ["starbucks"]},
            "actions": {"category": "travel"},
        },
    )
    drain(c)
    detail = c.get(f"/api/transactions/{t['id']}").json()
    assert detail["category"] == "Entertainment"
    assert "category" in detail["pinned_fields"]
    assert detail["document"]["filename"] == "fabrikam_card_2026-01.pdf"
    assert detail["source_ref"]["page"] == 1

    # reconciliation links are visible and reversible
    links = c.get("/api/reconciliation/links").json()
    summary = c.get("/api/reconciliation/summary").json()
    assert summary["to_review"] == sum(lk["status"] == "auto" for lk in links) > 0
    review = c.get(
        "/api/reconciliation/links", params={"status": "auto", "sort": "confidence"}
    ).json()
    assert [lk["confidence"] for lk in review] == sorted(lk["confidence"] for lk in review)
    transfer = next(lk for lk in links if lk["kind"] == "internal_transfer")
    assert (
        c.post(
            f"/api/reconciliation/links/{transfer['id']}", json={"status": "rejected"}
        ).status_code
        == 200
    )
    after = c.get("/api/reconciliation/summary").json()
    assert after["to_review"] == summary["to_review"] - 1
    assert after["by_status"]["rejected"]["internal_transfer"] == 1
    out = c.get(f"/api/transactions/{transfer['from_transaction_id']}").json()
    assert out["classification_method"] != "reconciliation"
    drain(c)
    # rejected pairs are not re-linked by later runs
    c.post("/api/reconciliation/run")
    drain(c)
    links = c.get("/api/reconciliation/links", params={"kind": "internal_transfer"}).json()
    assert [lk["status"] for lk in links] == ["rejected"]

    # config history and version are recorded
    hist = c.get("/api/config/history").json()
    assert any(h["action"] == "merge" for h in hist)

    # deleting a document removes its rows
    doc = next(d for d in docs if d["original_filename"].startswith("contoso"))
    before = c.get("/api/transactions", params={"document_id": doc["id"]}).json()
    assert before["total"] == 4
    assert [src["document_id"] for src in before["by_source"]] == [doc["id"]]
    listed = next(d for d in c.get("/api/documents").json() if d["id"] == doc["id"])
    assert listed["totals"]["count"] == 4
    r = c.delete(f"/api/documents/{doc['id']}")
    assert r.json()["deleted_transactions"] == 4
    after = c.get("/api/transactions", params={"document_id": doc["id"]}).json()
    assert after["total"] == 0 and after["by_source"] == []
    assert all(d["id"] != doc["id"] for d in c.get("/api/documents").json())


def test_backup(client):
    r = client.post("/api/backup").json()
    assert r["name"].endswith(".zip") and r["size_bytes"] > 0


def test_intelligence_config_validation(client):
    c = client
    bad = c.put(
        "/api/intelligence", json={"providers": [{"id": "Bad Id", "kind": "api", "model": "x"}]}
    )
    assert bad.status_code == 400
    ok = c.put(
        "/api/intelligence",
        json={
            "providers": [
                {
                    "id": "local",
                    "kind": "local",
                    "model": "ollama_chat/llama3.1",
                    "api_base": "http://127.0.0.1:11434",
                }
            ],
            "routing": {"default": ["local"]},
        },
    )
    assert ok.status_code == 200, ok.text
    cfg = c.get("/api/intelligence").json()
    assert cfg["providers"][0]["id"] == "local" and "classify" in cfg["tasks"]
