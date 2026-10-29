# Nabec Networks Connection website

A static site (no server needed) for https://nabec.co.ke, hosted free on Cloudflare.

| File | What it is |
|---|---|
| `index.html` | The page: services, memorial websites, prices, contact |
| `styles.css` | Colours and layout (lavender, plum and teal watercolour washes) |
| `logo-mark.svg` | The logo; also the browser tab icon |
| `logo-512.png` | Square logo for WhatsApp Business, Google and social profile photos |
| `og.png` | The preview image shown when the link is shared on WhatsApp or social media |

**Changing prices or text:** edit `index.html` (prices are in the `id="prices"` section),
then upload the folder to Cloudflare again.

**Publishing:** upload this folder's files to Cloudflare (Workers & Pages), then add the custom
domains `nabec.co.ke` and `www.nabec.co.ke`. Don't upload `README.md`.
