# Switching on M-Pesa giving

Giving is **off** until you set `MPESA_ENABLED=true`. Until then the page can still show a Paybill number for
people to pay from their M-Pesa menu (`DISPLAY_PAYBILL`, `DISPLAY_ACCOUNT`), and the treasurer records
those payments in the family area.

## 1. Who receives the money

M-Pesa Express sends money to a **Paybill or Till that belongs to the family** (or to a trusted family
member's business). It must be registered with Safaricom for M-Pesa Express (Lipa Na M-Pesa Online).
Agree in writing who controls it. This website records contributions; it never holds money.

## 2. Test in the sandbox first

1. Create an account at https://developer.safaricom.co.ke and an app with "M-Pesa Express (Sandbox)".
2. Put the app's keys into the server's secret files:
   ```sh
   printf '%s' 'CONSUMER_KEY'    > secrets/mpesa_consumer_key
   printf '%s' 'CONSUMER_SECRET' > secrets/mpesa_consumer_secret
   printf '%s' 'PASSKEY'         > secrets/mpesa_passkey
   ```
3. In `.env`: `MPESA_ENABLED=true`, `MPESA_ENV=sandbox`, `MPESA_SHORTCODE=174379`.
4. `make up`, then contribute KES 10 from the page with a sandbox test number.
5. Watch it settle in the family area → Contributions, and in Grafana.

## 3. Go live

1. Apply for production ("Go Live") on the Daraja portal with the family's shortcode. Safaricom emails the
   production passkey.
2. Replace the three secret files with the production values.
3. In `.env`: `MPESA_ENV=production`, `MPESA_SHORTCODE=<shortcode>`. For a **Till**:
   `MPESA_TRANSACTION_TYPE=CustomerBuyGoodsOnline`, `MPESA_SHORTCODE=<store number>`,
   `MPESA_PARTY_B=<till number>`.
4. Optional but recommended: `MPESA_CALLBACK_ALLOWED_IPS=` with the callback IPs Safaricom publishes.
5. `make up`, then make one real KES 10 contribution and check it against the M-Pesa statement.

The callback address is `https://<SITE_DOMAIN>/api/contributions/mpesa/callback/<secret>` and is sent to
Safaricom with each request; there is nothing to register by hand.

## How a contribution moves

```
pending ──callback success──► verifying ──status API confirms──► confirmed   (counted)
   │                              │
   │                              └──amount differs──► mismatch ──treasurer──► confirmed / void
   ├──cancelled on phone──► cancelled
   ├──no PIN entered──────► expired ──(late verified success)──► confirmed
   └──M-Pesa refused──────► failed
```

The reconciler checks every unsettled payment with Safaricom every 30 seconds, so a lost callback never
loses a contribution.

## Reconciling with the M-Pesa statement

Once a week, and after the fundraising closes:

1. Family area → Contributions → **Download CSV**.
2. Match each `confirmed` row's receipt number against the statement from the M-Pesa portal (or app).
3. Any statement line not in the ledger (for example someone paid from the M-Pesa menu): record it with
   **M-Pesa (sent directly to the family)** and its receipt number. Duplicates are refused automatically.
4. Review anything in **Needs review** with a note saying what you checked.
