import httpx
import respx

STORY = {
    "profile": {
        "full_name": "Martha Kemunto Ongosi",
        "known_as": "Mother of Anita",
        "born": "",
        "died": "",
        "birthplace": "",
        "resting_place": "",
        "epitaph": "Blessed are those who mourn.",
        "portrait_media_id": None,
        "service_date": "",
        "service_venue": "",
        "stream_url": "https://www.youtube.com/live/wOcYdCbTtgU",
        "updated_at": "2026-10-20T00:00:00Z",
    },
    "chapters": [
        {
            "id": "c1",
            "slug": "roots",
            "title": "Roots",
            "prompt": "Where her story began",
            "intro": "",
            "position": 10,
            "hidden": False,
            "entries": [
                {
                    "id": "e1",
                    "chapter_id": "c1",
                    "title": "<script>alert(1)</script>",
                    "period": "1950s",
                    "body": "Born in the hills.",
                    "media_id": None,
                    "caption": "",
                    "author_id": "u1",
                    "author_name": "Anita",
                    "relation": "Daughter",
                    "created_at": "2026-10-20T10:00:00Z",
                    "updated_at": "2026-10-20T10:00:00Z",
                }
            ],
        },
        {
            "id": "c9",
            "slug": "farewell",
            "title": "The Farewell",
            "prompt": "",
            "intro": "",
            "position": 90,
            "hidden": False,
            "entries": [],
        },
    ],
}


def mock_upstreams(story_status=200):
    respx.get("http://memorial.internal/api/memorial/story").mock(return_value=httpx.Response(story_status, json=STORY))
    respx.get("http://memorial.internal/api/memorial/tributes").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://memorial.internal/api/memorial/candles").mock(
        return_value=httpx.Response(200, json={"count": 3, "candles": []})
    )


@respx.mock
async def test_home_renders_story_escaped_with_og_tags(client):
    from app.main import app

    app.state.content._cache = None
    mock_upstreams()
    r = await client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "Martha Kemunto Ongosi" in html
    assert 'property="og:title"' in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "Support the family" not in html and "M-Pesa" not in html
    assert "Watch the burial service" in html
    assert "Chapter I" in html and "Chapter II" in html


@respx.mock
async def test_serves_last_good_copy_when_memorial_service_is_down(client):
    from app.main import app

    app.state.content._cache = None
    mock_upstreams()
    assert (await client.get("/")).status_code == 200
    app.state.content._cache = None
    respx.get("http://memorial.internal/api/memorial/story").mock(return_value=httpx.Response(503))
    r = await client.get("/")
    assert r.status_code == 200
    assert "Martha Kemunto Ongosi" in r.text
    assert "couldn't load" in r.text


async def test_family_invite_and_robots(client):
    family = await client.get("/family")
    assert family.status_code == 200
    assert "Save decision" not in family.text and "r-note" not in family.text
    assert (await client.get("/invite")).status_code == 200
    robots = (await client.get("/robots.txt")).text
    assert "Disallow: /family" in robots
    assert (await client.get("/static/memorial.js")).status_code == 200


@respx.mock
async def test_family_colour_choice_and_preview_bar(client):
    from app.main import app, templates

    app.state.content._cache = None
    story = {**STORY, "profile": {**STORY["profile"], "theme": "forest"}}
    respx.get("http://memorial.internal/api/memorial/story").mock(return_value=httpx.Response(200, json=story))
    respx.get("http://memorial.internal/api/memorial/tributes").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://memorial.internal/api/memorial/candles").mock(
        return_value=httpx.Response(200, json={"count": 0, "candles": []})
    )
    html = (await client.get("/")).text
    assert 'data-palette="forest"' in html
    assert "<title>Martha Kemunto Ongosi</title>" in html and "In loving memory" in html
    assert "Private preview" not in html
    templates.env.globals["site_preview"] = True
    try:
        app.state.content._cache = None
        html = (await client.get("/")).text
        assert "Private preview" in html and 'data-palette-choice="navy"' in html
    finally:
        templates.env.globals["site_preview"] = False


@respx.mock
async def test_family_heading_and_website_title(client):
    from app.main import app

    app.state.content._cache = None
    story = {**STORY, "profile": {**STORY["profile"], "heading": "Forever in our hearts", "site_title": "Mama Martha"}}
    respx.get("http://memorial.internal/api/memorial/story").mock(return_value=httpx.Response(200, json=story))
    respx.get("http://memorial.internal/api/memorial/tributes").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://memorial.internal/api/memorial/candles").mock(
        return_value=httpx.Response(200, json={"count": 0, "candles": []})
    )
    html = (await client.get("/")).text
    assert "<title>Mama Martha</title>" in html
    assert '<meta property="og:title" content="Mama Martha">' in html
    assert '<span class="label">Forever in our hearts</span>' in html
