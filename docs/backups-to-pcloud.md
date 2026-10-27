# Backups to pCloud

While the memorial runs on this computer (`make share`), it backs itself up about a minute
after each start and then once a day. With a pCloud account connected, every backup is also
copied there, so nothing is lost if this computer is lost or breaks.

## Connect pCloud (once)

The pCloud account owner needs to sign in once, on this computer:

```
make connect-pcloud
```

1. A link starting `http://127.0.0.1:53682/auth?...` appears. Copy it into Chrome or Edge.
2. Sign in to pCloud and click **Allow**.
3. Back in the terminal, it says **Connected**. Run `make share`.

Only an access key is kept, in `secrets/rclone.conf` on this computer. The pCloud password is
never stored, and nothing about pCloud is visible on the website.

## What appears in pCloud

In the **Martha Memoir** folder:

| Folder | What it holds |
|---|---|
| `Photos` | Every photograph added to the memorial, as ordinary JPG files named by the date they were added. Add-only: photos removed from the site stay here. |
| `Backups (encrypted)` | Full backups of stories, tributes, accounts and photos, for restoring the site. Kept for 90 days (`OFFSITE_KEEP_DAYS` in `.env`). |

To take a backup straight away: `make backup-now`.

## Keep the backup passphrase safe

The encrypted backups can only be opened with the passphrase in `secrets/backup_passphrase`.
**If this computer is lost, so is that file.** Save a copy now somewhere else, for example in a
password manager or printed and kept with family papers:

```
cat secrets/backup_passphrase
```

The `Photos` folder needs no passphrase.

## Restore the site from pCloud

1. In pCloud, open `Backups (encrypted)` and download the newest `.tar.gz.gpg` file and its
   `.sha256` file.
2. Put both in the `backups/archive` folder of the project (on a new computer, first run
   `make share` once and put the saved passphrase in `secrets/backup_passphrase`).
3. Run, with the file's name:

```
make restore-here file=backups/archive/20261027T030000Z.tar.gz.gpg
```

This replaces what the site currently shows with the backup, then starts it again.

## Stop sending backups to pCloud

Remove the `OFFSITE_REMOTE=` value in `.env` and run `make share`. To remove the access
completely, also delete `secrets/rclone.conf`.
