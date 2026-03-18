This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## QR Sharing (No App On Patient Phone)

Recommended for clinics: use LAN mode so patients do not need to install anything.

```bash
npm run share:lan:sync
```

This writes your local LAN base URL to `public/self-register-base.txt`. Patients on the same Wi-Fi can open the QR page directly in WeChat/Safari.

Optional environment variables:

```bash
LAN_HOST=192.168.1.100
LAN_PORT=3000
LAN_PROTOCOL=http
```

## Public 5G Access (No Same Wi-Fi)

If patients use mobile data (5G), they are not on your LAN. Use a public HTTPS URL.

### Fixed Public Domain + Reverse Proxy (Recommended)

1. Point your domain DNS A record to your server public IP.
2. In `emr/docker/.env.public`, configure:

```bash
PUBLIC_DOMAIN=your-domain.com
NEXT_PUBLIC_API_URL=/api
NEXT_PUBLIC_SELF_REGISTER_BASE_URL=https://your-domain.com
PUBLIC_WEB_BASE_URL=https://your-domain.com
```

3. Start services with Caddy reverse proxy (auto HTTPS):

```bash
cd /home/shuwen/emr/docker
docker compose -f docker-compose.prod.yml -f docker-compose.public-domain.yml --env-file .env.public up -d --build
```

4. Write fixed domain to QR base file:

```bash
cd /home/shuwen/emr/web
npm run share:public:sync
```

This gives a stable `https://your-domain.com/self-register` URL that works for WeChat/Safari on 5G.

### Quick Temporary Public Option

Quick option with Tailscale Funnel:

```bash
npm run share:funnel:sync
```

This command:

- exposes local port 3000 via Tailscale Funnel,
- writes a public HTTPS base URL to `public/self-register-base.txt`,
- makes the QR code usable from WeChat/Safari on mobile data.

Notes:

- this does not require patients to install Tailscale,
- your tailnet admin may need to enable Funnel once for this node,
- for long-term production, a dedicated domain + reverse proxy is still recommended.

### No Real Domain: Cloudflare Quick Tunnel

If you do not have a real domain yet, use a temporary public URL:

```bash
cd /home/shuwen/emr/web
npm run share:cloudflare:sync
```

This starts `cloudflared` quick tunnel and writes the temporary HTTPS URL into `public/self-register-base.txt` so the QR code can be opened on 5G.

Stop and clear it with:

```bash
npm run share:cloudflare:stop
```

Note: this URL is temporary and may change after restart.

## Tailscale QR Sharing (Optional)

Use this only when patients are inside your Tailscale network.

```bash
npm run share:tailscale:sync
```

The command writes the detected Tailscale web base to `public/self-register-base.txt`. When the QR modal opens on `/patients`, the page auto-loads that address and generates a mobile-accessible QR code.

Optional environment variables:

```bash
TAILSCALE_HOST=your-device-or-magicdns-name
TAILSCALE_PORT=3000
TAILSCALE_PROTOCOL=http
```

To clear the shared address:

```bash
npm run share:tailscale:clear
```

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
