from io import BytesIO

from PIL import Image

from .conftest import auth

EDITOR = auth("u-editor", "editor")
OTHER = auth("u-other", "editor")
OWNER = auth("u-owner", "owner")


def jpeg_with_gps() -> bytes:
    im = Image.new("RGB", (4000, 3000), (120, 80, 60))
    exif = Image.Exif()
    exif[0x8825] = {2: (1.0, 0.0, 0.0)}  # GPS IFD
    exif[0x010F] = "PhoneMaker"
    buf = BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


async def upload(client, data: bytes, headers=EDITOR, name="photo.jpg"):
    return await client.post("/api/media/upload", files={"file": (name, data, "image/jpeg")}, headers=headers)


async def test_upload_reencodes_strips_exif_and_resizes(client):
    r = await upload(client, jpeg_with_gps())
    assert r.status_code == 201, r.text
    body = r.json()
    assert max(body["width"], body["height"]) == 2400
    full = await client.get(body["url"])
    assert full.status_code == 200
    assert full.headers["content-type"] == "image/jpeg"
    assert "immutable" in full.headers["cache-control"]
    with Image.open(BytesIO(full.content)) as im:
        assert not im.getexif()
    thumb = await client.get(body["thumb_url"])
    with Image.open(BytesIO(thumb.content)) as im:
        assert max(im.size) == 640
    again = await client.get(body["url"], headers={"if-none-match": full.headers["etag"]})
    assert again.status_code == 304


async def test_rejects_non_images(client):
    r = await upload(client, b"<script>alert(1)</script>", name="evil.jpg")
    assert r.status_code == 422
    r = await upload(client, b"%PDF-1.4 fake", name="doc.pdf")
    assert r.status_code == 422


async def test_png_with_transparency_becomes_jpeg(client):
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    buf = BytesIO()
    im.save(buf, format="PNG")
    r = await upload(client, buf.getvalue(), name="logo.png")
    assert r.status_code == 201


async def test_visitors_cannot_upload(client):
    r = await client.post("/api/media/upload", files={"file": ("a.jpg", jpeg_with_gps(), "image/jpeg")})
    assert r.status_code == 401


async def test_only_uploader_or_owner_can_delete(client):
    mid = (await upload(client, jpeg_with_gps())).json()["id"]
    assert (await client.delete(f"/api/media/{mid}", headers=OTHER)).status_code == 403
    assert (await client.delete(f"/api/media/{mid}", headers=OWNER)).status_code == 204
    assert (await client.get(f"/api/media/{mid}")).status_code == 404


async def test_bad_ids_are_not_found(client):
    assert (await client.get("/api/media/..%2F..%2Fetc%2Fpasswd")).status_code == 404
    assert (await client.get("/api/media/" + "z" * 32)).status_code == 404
