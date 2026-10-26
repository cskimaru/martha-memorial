from .conftest import auth

OWNER = auth("u-owner", "owner")
EDITOR = auth("u-editor", "editor")
EDITOR2 = auth("u-editor2", "editor")


async def test_story_is_seeded_with_martha_and_chapters(client):
    r = await client.get("/api/memorial/story")
    assert r.status_code == 200
    data = r.json()
    assert data["profile"]["full_name"] == "Martha Kemunto Ongosi"
    titles = [c["title"] for c in data["chapters"]]
    assert titles[0] == "Roots" and titles[-1] == "The Farewell"
    assert len(titles) == 9


async def test_visitors_cannot_write(client):
    story = (await client.get("/api/memorial/story")).json()
    ch = story["chapters"][0]["id"]
    r = await client.post("/api/memorial/entries", json={"chapter_id": ch, "body": "x", "author_name": "x"})
    assert r.status_code == 401
    r = await client.put("/api/memorial/profile", json={"full_name": "Someone else"})
    assert r.status_code == 401


async def test_editor_adds_entry_and_only_author_or_owner_can_change_it(client):
    story = (await client.get("/api/memorial/story")).json()
    ch = story["chapters"][3]["id"]
    r = await client.post(
        "/api/memorial/entries",
        json={
            "chapter_id": ch,
            "title": "Sunday chapati",
            "body": "She made chapati every Sunday.",
            "author_name": "Anita",
            "relation": "Daughter",
        },
        headers=EDITOR,
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert (await client.patch(f"/api/memorial/entries/{eid}", json={"title": "x"}, headers=EDITOR2)).status_code == 403
    assert (await client.patch(f"/api/memorial/entries/{eid}", json={"period": "1990s"}, headers=EDITOR)).json()[
        "period"
    ] == "1990s"
    assert (await client.delete(f"/api/memorial/entries/{eid}", headers=OWNER)).status_code == 204
    story = (await client.get("/api/memorial/story")).json()
    assert all(e["id"] != eid for c in story["chapters"] for e in c["entries"])


async def test_entry_validation(client):
    story = (await client.get("/api/memorial/story")).json()
    ch = story["chapters"][0]["id"]
    r = await client.post("/api/memorial/entries", json={"chapter_id": ch, "author_name": "A"}, headers=EDITOR)
    assert r.status_code == 422
    r = await client.post(
        "/api/memorial/entries",
        json={"chapter_id": ch, "body": "x", "author_name": "A", "media_id": "../../etc/passwd"},
        headers=EDITOR,
    )
    assert r.status_code == 422


async def test_public_tribute_waits_for_approval(client):
    r = await client.post("/api/memorial/tributes", json={"name": "Neighbour", "message": "She was kind to everyone."})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["status"] == "pending"
    public = (await client.get("/api/memorial/tributes")).json()
    assert all(t["id"] != tid for t in public)
    assert (await client.get("/api/memorial/tributes", params={"status": "pending"})).status_code == 403
    r = await client.post(f"/api/memorial/tributes/{tid}/moderate", json={"status": "approved"}, headers=EDITOR)
    assert r.status_code == 200
    public = (await client.get("/api/memorial/tributes")).json()
    assert any(t["id"] == tid for t in public)


async def test_honeypot_tribute_is_dropped(client):
    r = await client.post(
        "/api/memorial/tributes", json={"name": "Bot", "message": "buy now", "website": "spam.example"}
    )
    assert r.status_code == 201
    pending = (await client.get("/api/memorial/tributes", params={"status": "pending"}, headers=EDITOR)).json()
    assert all(t["name"] != "Bot" for t in pending)


async def test_tribute_rate_limit(client):
    for _ in range(5):
        assert (
            await client.post("/api/memorial/tributes", json={"name": "A", "message": "hello there"})
        ).status_code == 201
    assert (
        await client.post("/api/memorial/tributes", json={"name": "A", "message": "hello there"})
    ).status_code == 429


async def test_candles(client):
    r = await client.post("/api/memorial/candles", json={"name": "Kerubo", "note": "Rest well, Mama"})
    assert r.status_code == 201
    data = (await client.get("/api/memorial/candles")).json()
    assert data["count"] >= 1
    cid = r.json()["id"]
    assert (await client.delete(f"/api/memorial/candles/{cid}", headers=EDITOR)).status_code == 204
    data = (await client.get("/api/memorial/candles")).json()
    assert all(c["id"] != cid for c in data["candles"])


async def test_profile_update_and_url_validation(client):
    bad = await client.put(
        "/api/memorial/profile",
        json={"full_name": "Martha Kemunto Ongosi", "stream_url": "javascript:alert(1)"},
        headers=EDITOR,
    )
    assert bad.status_code == 422
    ok = await client.put(
        "/api/memorial/profile", json={"full_name": "Martha Kemunto Ongosi", "resting_place": "Kisii"}, headers=EDITOR
    )
    assert ok.status_code == 200
    assert ok.json()["resting_place"] == "Kisii"


async def test_chapter_hide_and_add(client):
    r = await client.post("/api/memorial/chapters", json={"title": "Her Garden"}, headers=EDITOR)
    assert r.status_code == 201
    cid = r.json()["id"]
    await client.patch(f"/api/memorial/chapters/{cid}", json={"hidden": True}, headers=EDITOR)
    public = (await client.get("/api/memorial/story")).json()
    assert all(c["id"] != cid for c in public["chapters"])
    as_editor = (await client.get("/api/memorial/story", headers=EDITOR)).json()
    assert any(c["id"] == cid for c in as_editor["chapters"])


async def test_family_chooses_colour_scheme(client):
    story = (await client.get("/api/memorial/story")).json()
    assert story["profile"]["theme"] == "plum"
    ok = await client.put(
        "/api/memorial/profile", json={"full_name": "Martha Kemunto Ongosi", "theme": "forest"}, headers=EDITOR
    )
    assert ok.status_code == 200 and ok.json()["theme"] == "forest"
    bad = await client.put(
        "/api/memorial/profile", json={"full_name": "Martha Kemunto Ongosi", "theme": "neon"}, headers=EDITOR
    )
    assert bad.status_code == 422
