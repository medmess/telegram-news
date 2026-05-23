# GFN.TV Telegram News Collector

Python Telethon worker that reads image posts from `@Offsideahdaff`, filters
football-related captions, downloads the image, and sends the post to the
GFN.TV backend.

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
BACKEND_NEWS_ENDPOINT=https://fantasy-2wc5.onrender.com/api/news/telegram
SOURCE_NAME=Offside
LATEST_POST_LIMIT=15
```

Do not commit `.env`, `*.session`, `downloads/`, or logs.
