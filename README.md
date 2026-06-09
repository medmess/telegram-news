# Futivo / Le Lien Telegram News Collector

Python Telethon worker that reads football image posts from Telegram channels,
filters sports-related captions, compresses images, avoids duplicates, and sends
the posts to the Futivo backend.

Current sources:

- `@Offsideahdaff` -> `Offside`
- `@Erupean_sportt` -> `European Sport`
- `@infosportz` -> `Info Sportz`
- `@infosportsplus` -> `Info Sports Plus`

The Futivo app shows the Futivo sources. The Le Lien edition shows the French
sources `Info Sportz`, `Info Sports Plus`, and manual posts from `Le Lien Admin`.

## Render Background Worker

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
python main.py
```

Environment variables:

```env
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
STRING_SESSION=your_telethon_string_session
CHANNEL_USERNAME=Offsideahdaff
ADDITIONAL_CHANNELS=Erupean_sportt,infosportz,infosportsplus
CHANNEL_SOURCE_NAMES=Offsideahdaff=Offside,Erupean_sportt=European Sport,infosportz=Info Sportz,infosportsplus=Info Sports Plus
BACKEND_NEWS_ENDPOINT=https://fantasy-2wc5.onrender.com/api/news/telegram
SOURCE_NAME=Offside
LATEST_POST_LIMIT=15
```

Do not commit `.env`, `*.session`, `downloads/`, or logs.

## GitHub Actions Free Scheduled Mode

The included workflow runs every 15 minutes and executes the collector once.
It fetches the latest posts, sends new posts to the backend, then exits.

Required repository secrets:

```env
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
STRING_SESSION=your_telethon_string_session
BACKEND_NEWS_ENDPOINT=https://fantasy-2wc5.onrender.com/api/news/telegram
```

The workflow already sets these non-secret source variables:

```env
CHANNEL_USERNAME=Offsideahdaff
ADDITIONAL_CHANNELS=Erupean_sportt,infosportz,infosportsplus
CHANNEL_SOURCE_NAMES=Offsideahdaff=Offside,Erupean_sportt=European Sport,infosportz=Info Sportz,infosportsplus=Info Sports Plus
LATEST_POST_LIMIT=15
RUN_ONCE=true
```

Do not commit `.env`, `*.session`, `*.session-journal`, `downloads/`, logs, or
Python cache files.
