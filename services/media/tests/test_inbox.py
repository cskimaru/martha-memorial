from io import BytesIO

from PIL import Image

from .conftest import auth

EDITOR = auth("u-editor", "editor")


def jpeg(colour=(30, 90, 60)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (800, 600), colour).save(buf, format="JPEG")
    return buf.getvalue()


async def test_shared_photos_wait_for_review(client, tmp_path):
    from app import inbox
    from app.main import app

    app.state.settings.inbox_dir = str(tmp_path)
    (tmp_path / "Mama_at_church-1985.jpg").write_bytes(jpeg())
    (tmp_path / "IMG_2041.JPG").write_bytes(jpeg((200, 10, 10)))
    (tmp_path / "copy of mama.jpg").write_bytes(jpeg())  # the same photo again
    (tmp_path / "notes.txt").write_bytes(b"not a photo")
    (tmp_path / ".partial-upload.jpg").write_bytes(b"still arriving")

    assert await inbox.import_once(app) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == [".failed", ".partial-upload.jpg"]
    assert [p.name for p in (tmp_path / ".failed").iterdir()] == ["notes.txt"]

    assert (await client.get("/api/media/review")).status_code == 401
    waiting = (await client.get("/api/media/review", headers=EDITOR)).json()
    assert sorted(w["caption"] for w in waiting) == ["", "Mama at church 1985"]

    keep = next(w for w in waiting if w["caption"])
    drop = next(w for w in waiting if not w["caption"])
    assert (await client.get(keep["thumb_url"])).status_code == 200
    r = await client.post(f"/api/media/{keep['id']}/review", json={"status": "approved"}, headers=EDITOR)
    assert r.status_code == 204
    r = await client.post(f"/api/media/{drop['id']}/review", json={"status": "rejected"}, headers=EDITOR)
    assert r.status_code == 204
    assert (await client.get("/api/media/review", headers=EDITOR)).json() == []
    assert (await client.get(keep["url"])).status_code == 200
    assert (await client.get(drop["url"])).status_code == 404
    again = await client.post(f"/api/media/{keep['id']}/review", json={"status": "rejected"}, headers=EDITOR)
    assert again.status_code == 404

    # Dropping an approved photo in again doesn't queue it a second time.
    (tmp_path / "Mama again.jpg").write_bytes(jpeg())
    assert await inbox.import_once(app) == 0


async def test_site_uploads_are_not_reviewed(client):
    r = await client.post("/api/media/upload", files={"file": ("a.jpg", jpeg((1, 2, 3)), "image/jpeg")}, headers=EDITOR)
    assert r.status_code == 201
    assert all(w["id"] != r.json()["id"] for w in (await client.get("/api/media/review", headers=EDITOR)).json())


def test_captions_from_file_names():
    from app.names import caption_from_name as c

    assert c("Mama_at_church-1985.jpg") == "Mama at church 1985"
    assert c("1730000000-Grandma with the cows.png") == "Grandma with the cows"
    assert c("Mama (2).jpg") == "Mama"
    for camera in ["IMG_2041.JPG", "WhatsApp Image 2026-10-27 at 13.45.58.jpeg", "PXL_20240101_123456789.jpg",
                   "20240101_101010.jpg", "DSC01234.JPG", "photo.jpg"]:  # fmt: skip
        assert c(camera) == ""
