# Share the memorial from your own computer (free, no card)

Runs the whole memorial on your computer and gives you a public `https://…trycloudflare.com` link through a
free Cloudflare quick tunnel. No Cloudflare account, no card, no server. Good for showing the client and
letting the family start adding content while you wait to set up proper hosting.

**Limits to know:**

* The link works only while your computer is on, awake and online, with `make share` running.
* With the free quick link, `make share` keeps the same link while the tunnel keeps running (also after
  updates). Restarting the computer or `make share-new` gives a **new** link. For an address that never
  changes, with her name in it, see [A permanent address](#a-permanent-address-with-her-name).
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
| Start sharing, or update after `git pull` (keeps the link) | `make share` |
| Start with a fresh quick link | `make share-new` |
| Stop sharing | `make share-stop` |
| See what's running | `make ps` |
| Something looks wrong | `make logs s=web` (or `memorial`, `auth`, `media`, `caddy`, `cloudflared`) |
| Get the latest version from GitHub | `git pull`, then `make share` (same link) |
| Take a backup | `make backup-now` |

The site stays password-protected (`SITE_PREVIEW=true` in `.env`) so only people with the login can see it.

## A permanent address with her name

Instead of a random link, the memorial can be at your own address, for example
`https://marthaongosi.co.ke`, still served from this computer. It stays the same when you restart or update,
and later it moves to a real server unchanged. You need a domain name (about KES 1,000–1,500 a year) and a
free Cloudflare account.

1. **Buy the domain** from a Kenyan registrar that accepts M-Pesa (search "co.ke domain M-Pesa"). Choose the
   name the family will recognise, such as `marthaongosi.co.ke` or `mamamartha.co.ke`.
2. **Create a free Cloudflare account** at https://dash.cloudflare.com/sign-up.
3. **Add the domain to Cloudflare:** *Add a domain* → type it → choose the **Free** plan. Cloudflare shows two
   *nameservers*. In your registrar's control panel, replace the domain's nameservers with those two. Cloudflare
   emails you when the domain is **Active** (usually within an hour, at most a day).
4. **Create the tunnel:** in Cloudflare open **Zero Trust** → **Networks** → **Tunnels** → **Create a
   tunnel** → **Cloudflared** → name it `martha-memorial`. On the install page, copy the long **token** (the
   text after `--token` in the command shown). You don't need to run that command.
5. **Point the address at the memorial:** in the tunnel's **Public hostname** (also called *Published
   application routes*) add: subdomain empty, domain `marthaongosi.co.ke`, type **HTTP**, URL `caddy:80`. Save.
6. **On this computer**, put both in `.env` (`nano .env`):
   ```
   PUBLIC_HOSTNAME=marthaongosi.co.ke
   CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoi...the long token...
   ```
   then run `make share`. It now prints `https://marthaongosi.co.ke`, every time.

If the Zero Trust page asks for a payment method before letting you use the free plan, tell the person
helping you: there is a way to create the tunnel from the command line instead.

Keep the token private: anyone who has it can put a site on your address.

## Moving to real hosting later

1. `make backup-now`.
2. Keep `.env`, the `secrets/` folder and the newest file in `backups/archive/`.
3. On the server, follow [free-hosting-oracle.md](free-hosting-oracle.md) (or any Ubuntu server) and its
   "Moving to a paid server" section, which restores that backup. Everything the family added comes across.
