# Share the memorial from your own computer (free, no card)

Runs the whole memorial on your computer and gives you a public `https://…trycloudflare.com` link through a
free Cloudflare quick tunnel. No Cloudflare account, no card, no server. Good for showing the client and
letting the family start adding content while you wait to set up proper hosting.

**Limits to know:**

* The link works only while your computer is on, awake and online, with `make share` running.
* Each time you start it you get a **new** link; send the new one to the client.
* Quick tunnels are meant for testing and come without any uptime guarantee from Cloudflare.
* Stories and photos are stored on your computer. They move to the real server later with a backup and
  restore (see the end).

## 1. Install the tools (once)

* **Windows 10/11:** install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and let it
  turn on WSL 2. Then open the **Ubuntu** app (install it from the Microsoft Store if it isn't there) and run
  every command below inside it. First: `sudo apt update && sudo apt install -y make git`.
* **Mac:** install [Docker Desktop](https://www.docker.com/products/docker-desktop/). Open **Terminal** and run
  `make --version`; if asked to install developer tools, accept.
* **Linux:** install Docker (`curl -fsSL https://get.docker.com | sudo sh`), `make` and `git`.

Start Docker Desktop and wait until it says it is running.

## 2. Get the code (once)

```sh
git clone https://github.com/cskimaru/martha-memorial.git
cd martha-memorial
```

The repository is private, so git asks you to sign in. Use your GitHub username and, as the password, a
**personal access token**: GitHub → your photo → **Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token**, with access to `martha-memorial` and *Contents: Read-only*.

## 3. Share it

```sh
make share
```

The first time this builds everything, which takes several minutes. It ends with:

```
The memorial is shared at:  https://some-random-words.trycloudflare.com
Preview login:             user 'family', password '…'
On this computer:          http://localhost:8080
```

Send the client the link and the preview login.

The first time only, create your own family account, then sign in at `<link>/family`:

```sh
make create-owner email=cskimaru@gmail.com name="Your Name"
```

From the family area you can invite relatives to add stories and photos, and set her details and the colour
scheme ("Edit her details" on the memorial page).

## Every day

| Task | Command |
|---|---|
| Start sharing again (new link) | `make share` |
| Stop sharing | `make share-stop` |
| See what's running | `make ps` |
| Something looks wrong | `make logs s=web` (or `memorial`, `auth`, `media`, `caddy`, `cloudflared`) |
| Get the latest version from GitHub | `git pull`, then `make share` |
| Take a backup | `make backup-now` |

The site stays password-protected (`SITE_PREVIEW=true` in `.env`) so only people with the login can see it.

## Moving to real hosting later

1. `make backup-now`.
2. Keep `.env`, the `secrets/` folder and the newest file in `backups/archive/`.
3. On the server, follow [free-hosting-oracle.md](free-hosting-oracle.md) (or any Ubuntu server) and its
   "Moving to a paid server" section, which restores that backup. Everything the family added comes across.
