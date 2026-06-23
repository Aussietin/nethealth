# NetHealth Web Dashboard

This is the frontend for the NetHealth network diagnostic tool. It is built with **Next.js** and features a high-contrast **Cyberpunk** aesthetic.

## Features

- **Real-time Monitoring**: Visualizes ping latency and packet loss via WebSockets.
- **Cyberpunk UI**: High-performance interface with neon-green themes and interactive glitch effects.
- **Responsive Design**: Works on mobile and desktop browsers.

## Getting Started

The recommended way to run this dashboard is via the root `manage.py` script:

```bash
# From the project root
python manage.py dev
```

### Manual Development

If you need to run the frontend independently:

1. Install dependencies:
   ```bash
   npm install
   ```
2. Start the dev server:
   ```bash
   npm run dev
   ```

The dashboard will be available at [http://localhost:3000](http://localhost:3000). It expects the Backend API to be running on [http://localhost:8000](http://localhost:8000).

## Architecture

- **Framework**: Next.js 15 (App Router)
- **Styling**: Tailwind CSS with custom neon utilities.
- **State Management**: React Hooks.
- **Communication**: WebSockets (for monitoring) and REST (for snapshot checks).
