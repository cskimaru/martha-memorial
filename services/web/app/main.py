import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from memorial_common.app import create_app
from memorial_common.security import ACCESS_COOKIE

from .config import get_settings
from .content import ContentClient

HERE = Path(__file__).parent
settings = get_settings()


async def shutdown(app: FastAPI) -> None:
    await app.state.content.close()


app = create_app(settings, title="Memorial web", on_shutdown=shutdown)
app.state.content = ContentClient(settings)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

ROMAN = [
    "",
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
    "XI",
    "XII",
    "XIII",
    "XIV",
    "XV",
    "XVI",
    "XVII",
    "XVIII",
    "XIX",
    "XX",
]


def roman(n: int) -> str:
    return ROMAN[n] if 0 < n < len(ROMAN) else str(n)


def nice_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%-d %B %Y")
    except (ValueError, AttributeError):
        return ""


def initials(name: str) -> str:
    return "".join(p[0] for p in name.split()[:3]).upper()


templates.env.filters["roman"] = roman
templates.env.filters["nice_date"] = nice_date
templates.env.filters["initials"] = initials


def static_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.is_file():
            digest.update(f.relative_to(root).as_posix().encode())
            digest.update(f.read_bytes())
    return digest.hexdigest()[:12]


templates.env.globals["asset_version"] = settings.asset_version or static_fingerprint(HERE / "static")
templates.env.globals["site_origin"] = settings.site_origin
templates.env.globals["site_preview"] = settings.site_preview
# (key, name shown to people). Keys are kept from the first version so saved choices keep working.
templates.env.globals["palettes"] = [
    ("plum", "Lavender evening"),
    ("charcoal", "Morning light"),
    ("forest", "Garden"),
    ("navy", "Still waters"),
    ("burgundy", "Rose dusk"),
]

NO_STORE = {"Cache-Control": "no-store"}


def auth_headers(request: Request) -> dict | None:
    token = request.cookies.get(ACCESS_COOKIE)
    return {"cookie": f"{ACCESS_COOKIE}={token}"} if token else None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    data = await request.app.state.content.page(auth_headers(request))
    story = data.story or {"profile": None, "chapters": []}
    profile = story.get("profile") or {"full_name": "Martha Kemunto Ongosi", "known_as": "Mother of Anita"}
    photos = [e for c in story["chapters"] for e in c["entries"] if e.get("media_id")]
    signed_in = auth_headers(request) is not None
    resp = templates.TemplateResponse(
        request,
        "index.html",
        {
            "profile": profile,
            "theme": profile.get("theme") or "plum",
            "chapters": story["chapters"],
            "photos": photos,
            "tributes": data.tributes,
            "candles": data.candles,
            "degraded": data.degraded,
        },
        headers=NO_STORE if signed_in else {"Cache-Control": "public, max-age=15"},
    )
    return resp


@app.get("/family", response_class=HTMLResponse)
async def family(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "family.html", {}, headers=NO_STORE)


@app.get("/invite", response_class=HTMLResponse)
async def invite(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "invite.html", {}, headers=NO_STORE)


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots() -> str:
    return "User-agent: *\nDisallow: /family\nDisallow: /invite\nDisallow: /api/\n"
