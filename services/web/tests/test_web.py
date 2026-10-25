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
GIVING = {
    "giving_open": True,
    "total": 125000,
    "count": 12,
    "currency": "KES",
    "contributors": [{"name": "Kerubo", "amount": None, "message": ""}],
    "paybill": "247247",
    "account": "Martha",
    "min_amount": 10,
    "max_amount": 250000,
}


def mock_upstreams(story_status=200):
    respx.get("http://memorial.internal/api/memorial/story").mock(return_value=httpx.Response(story_status, json=STORY))
    respx.get("http://memorial.internal/api/memorial/tributes").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://memorial.internal/api/memorial/candles").mock(
        return_value=httpx.Response(200, json={"count": 3, "candles": []})
    )
    respx.get("http://contributions.internal/api/contributions/summary").mock(
        return_value=httpx.Response(200, json=GIVING)
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
    assert "KES 125,000" in html
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
    assert (await client.get("/family")).status_code == 200
    assert (await client.get("/invite")).status_code == 200
    robots = (await client.get("/robots.txt")).text
    assert "Disallow: /family" in robots
    assert (await client.get("/static/memorial.js")).status_code == 200
