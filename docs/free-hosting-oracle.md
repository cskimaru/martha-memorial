# Free hosting on Oracle Cloud with a DuckDNS address

This puts the memorial on a free Oracle Cloud server, at a free address like
`https://martha-memorial.duckdns.org`, in **private preview** (password-protected) until you're ready.
Later you can move everything to a paid server without losing anything (last section).

Allow about an hour the first time. You need a bank card for Oracle's identity check; Oracle does not charge
while you stay inside the free limits described here.

> Oracle's free allowance for this kind of server is **2 CPUs and 12 GB of memory** (reduced from 4 and 24 in
> June 2026). The memorial needs about 3 GB, so this is plenty. Check Oracle's
> [Always Free page](https://www.oracle.com/cloud/free/) for the current limits when you sign up.

---

## 1. Create the Oracle Cloud account

1. Go to https://www.oracle.com/cloud/free/ and choose **Start for free**.
2. Fill in your details and verify the card.
3. **Home region:** this can never be changed, and free servers can only be created in it. Pick the region
   closest to Kenya that the form offers (for example *South Africa Central (Johannesburg)*).
4. Wait for the "account is ready" email, then sign in at https://cloud.oracle.com.

### Protect the server from being reclaimed (recommended)

Oracle may reclaim free servers that stay almost idle for a week, and a quiet memorial can look idle. To
prevent this, upgrade the account to **Pay As You Go**: top-right menu → **Upgrade and Manage Payment** →
**Upgrade your account**. Free resources stay free. Then add a safety net so you hear about any charge:
menu → **Billing & Cost Management** → **Budgets** → **Create Budget**, amount `1` (USD), alert at 100%,
your email.

## 2. Get the free address from DuckDNS

1. Go to https://www.duckdns.org and sign in (Google or GitHub).
2. Under **sub domain**, type a name such as `martha-memorial` and press **add domain**.
3. Leave the page open: you'll need the **token** shown at the top, and you'll fill in the IP address later
   (the setup script does it for you).

Your address is now `martha-memorial.duckdns.org` (use your own name everywhere below).

## 3. Create the server

1. In the Oracle console: menu (☰) → **Compute** → **Instances** → **Create instance**.
2. **Name:** `martha-memorial`.
3. **Image and shape** → **Edit**:
   * **Image:** *Change image* → **Canonical Ubuntu** → **24.04** (make sure it is the *aarch64* build).
   * **Shape:** *Change shape* → **Ampere** → **VM.Standard.A1.Flex** → **2 OCPUs**, **12 GB memory**.
     The page should show "Always Free-eligible".
4. **Networking:** keep *Create new virtual cloud network* and *Create new public subnet*, and make sure
   **Assign a public IPv4 address** is on.
5. **Add SSH keys:** choose **Generate a key pair for me** and click **Save private key**. Keep that file
   safe: it is the only way into the server.
6. **Boot volume:** tick *Specify a custom boot volume size* and enter **100** GB (up to 200 GB is free).
7. **Create.** After a minute or two the instance shows **Running**. Copy its **Public IP address**.

**"Out of capacity" error?** Oracle sometimes has no free ARM machines left in a region. Try a different
*Availability domain* on the same page, or try again later in the day; it usually works within a few tries.

### Open the web ports in Oracle's firewall

1. On the instance page, click the **Subnet** link, then the **Default Security List**.
2. **Add Ingress Rules**, three times:
   * Source CIDR `0.0.0.0/0`, IP protocol **TCP**, destination port **80**
   * Source CIDR `0.0.0.0/0`, IP protocol **TCP**, destination port **443**
   * Source CIDR `0.0.0.0/0`, IP protocol **UDP**, destination port **443**

## 4. Connect to the server

On your computer, in a terminal (Windows: *PowerShell*):

```sh
ssh -i path/to/ssh-key-XXXX.key ubuntu@<public-ip>
```

On Mac or Linux, if it complains about permissions, run `chmod 600 path/to/ssh-key-XXXX.key` first.
Everything below is typed on the server.

## 5. Get the code onto the server

The repository is private, so the server needs a read-only key for it.

```sh
ssh-keygen -t ed25519 -N "" -f ~/.ssh/github_deploy -C "martha-memorial server"
cat ~/.ssh/github_deploy.pub
```

Copy the line it prints. On GitHub open **cskimaru/martha-memorial → Settings → Deploy keys → Add deploy
key**, paste it, name it `oracle server`, leave *Allow write access* **off**, and save. Then:

```sh
printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n' >> ~/.ssh/config
git clone git@github.com:cskimaru/martha-memorial.git
cd martha-memorial
```

(Answer `yes` when asked whether to trust github.com.)

## 6. Prepare the server

Replace the name and token with yours from step 2:

```sh
./scripts/setup-ubuntu-server.sh martha-memorial YOUR-DUCKDNS-TOKEN
```

It installs Docker, opens ports 80 and 443 in Ubuntu's own firewall (Oracle's Ubuntu blocks them by default),
and sets DuckDNS to this server's address, re-checking every 5 minutes. It should finish with
`DuckDNS answered: OK`. Then **log out and back in** (`exit`, then the ssh command again) and
`cd martha-memorial`.

## 7. Configure the memorial

```sh
make init
nano .env
```

In `.env` set:

```
SITE_DOMAIN=martha-memorial.duckdns.org
ACME_EMAIL=cskimaru@gmail.com
SITE_PREVIEW=true
```

Save (`Ctrl+O`, `Enter`, `Ctrl+X`), then:

```sh
make init
```

It prints the **preview login**: user `family` and a password. Write it down; it is also in
`secrets/preview_password`.

**Copy `secrets/backup_passphrase` somewhere safe off the server** (a password manager, or printed). Backups
cannot be opened without it.

## 8. Build and start

```sh
make build      # 10–20 minutes the first time: builds everything for this ARM server
make up
```

`make up` waits until every part reports healthy. Then create your own account:

```sh
make create-owner email=cskimaru@gmail.com name="Your Name"
```

## 9. Check it

Open `https://martha-memorial.duckdns.org`. The browser asks for the preview login, then shows the memorial
with the "Private preview" bar and the colour switcher. The padlock should show a valid certificate (it can
take a minute after the first start).

```sh
PREVIEW_PASSWORD=$(cat secrets/preview_password) make smoke url=https://martha-memorial.duckdns.org
```

should end with `All checks passed.`

Now:

* Sign in at `/family`, open **Edit her details** on the memorial page and fill in what you know.
* Invite family members from `/family` → **Family members**; send each their invitation link privately.
* Send reviewers the address and the preview login.

## Everyday

| Task | On the server, in `~/martha-memorial` |
|---|---|
| Is everything running? | `make ps` |
| Something looks wrong | `make logs s=web` (or `memorial`, `auth`, `media`, `caddy`) |
| Install the latest version from GitHub | `git pull && make build && make up` |
| Take a backup now | `make backup-now` |
| Launch publicly | set `SITE_PREVIEW=false` in `.env`, then `make init && make up` |

Monitoring dashboards: see [runbook.md](runbook.md#monitoring) (add `-i path/to/ssh-key-XXXX.key` to the
ssh command shown there).

## If something goes wrong

| Problem | What to check |
|---|---|
| The site doesn't load at all | `make ps` shows everything Up? Oracle security list has ports 80/443 (step 3)? `cat ~/.duckdns/last.log` says `OK`? `ping martha-memorial.duckdns.org` shows the server's IP? |
| Browser warns about the certificate | Wait a few minutes after the first start, then `make logs s=caddy`. Ports 80 and 443 must be reachable from the internet for the certificate to be issued. |
| `make build` fails with a network error | Run it again; downloads sometimes time out. |
| "permission denied" from Docker | You haven't logged out and back in since step 6. |
| The server disappeared or was stopped by Oracle | See "Protect the server from being reclaimed" in step 1. Restore from your backups onto a new server (below). |

## Moving to a paid server later

When the client pays, move to a paid server (any Ubuntu server with at least 2 GB of memory) and a proper
domain:

1. On the Oracle server: `make backup-now`.
2. Copy these to your computer: `.env`, the whole `secrets/` folder, and the newest file in
   `backups/archive/` (for example with `scp -i key -r ubuntu@<ip>:martha-memorial/secrets .`).
3. On the new server: steps 5 and 6 (without the DuckDNS arguments if you use a real domain), then put `.env`
   and `secrets/` in place, change `SITE_DOMAIN` to the new domain, and copy the archive into
   `backups/archive/`.
4. `make init && make build && make up`, then
   `make restore file=backups/archive/<the archive>.tar.gz.gpg`.
5. Point the domain's DNS `A` record at the new server. Check the site, then delete the Oracle instance.

All stories, photos, tributes, candles and family accounts come across unchanged.
