import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
import zlib
from datetime import timezone
from pathlib import Path
from urllib import error, request

from telethon import TelegramClient, events
from telethon.sessions import StringSession


BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
ENV_PATH = BASE_DIR / ".env"


def load_env(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key):
            os.environ[key] = value


load_env(ENV_PATH)

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "Offsideahdaff")
ADDITIONAL_CHANNELS = os.getenv("ADDITIONAL_CHANNELS", "Erupean_sportt")
CHANNEL_SOURCE_NAMES = os.getenv(
    "CHANNEL_SOURCE_NAMES",
    "Offsideahdaff=Offside,Erupean_sportt=European Sport",
)
BACKEND_NEWS_ENDPOINT = os.getenv(
    "BACKEND_NEWS_ENDPOINT",
    "https://fantasy-2wc5.onrender.com/api/news/telegram",
)
SESSION_NAME = os.getenv("SESSION_NAME", "fantasy_session")
STRING_SESSION = os.getenv("STRING_SESSION", "")
SOURCE_NAME = os.getenv("SOURCE_NAME", "Offside")
LATEST_POST_LIMIT = int(os.getenv("LATEST_POST_LIMIT", "15"))
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() in {"1", "true", "yes"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("telegram-news")

session = StringSession(STRING_SESSION) if STRING_SESSION else str(BASE_DIR / SESSION_NAME)
client = TelegramClient(session, API_ID, API_HASH)
processed_post_ids: set[tuple[str, int]] = set()
seen_post_fingerprints: set[str] = set()

SPORT_KEYWORDS = (
    "football",
    "soccer",
    "world cup",
    "fifa",
    "uefa",
    "caf",
    "match",
    "matches",
    "goal",
    "goals",
    "assist",
    "player",
    "coach",
    "club",
    "team",
    "league",
    "premier",
    "laliga",
    "serie a",
    "bundesliga",
    "ligue 1",
    "champions league",
    "transfer",
    "ballon d'or",
    "\u0643\u0623\u0633 \u0627\u0644\u0639\u0627\u0644\u0645",
    "\u0645\u0648\u0646\u062f\u064a\u0627\u0644",
    "\u0627\u0644\u0641\u064a\u0641\u0627",
    "\u0641\u064a\u0641\u0627",
    "\u0643\u0631\u0629",
    "\u0627\u0644\u0642\u062f\u0645",
    "\u0645\u0628\u0627\u0631",
    "\u0645\u0628\u0627\u0631\u0627\u0629",
    "\u0645\u0628\u0627\u0631\u064a\u0627\u062a",
    "\u0645\u0646\u062a\u062e\u0628",
    "\u0645\u0646\u062a\u062e\u0628\u0627\u062a",
    "\u0644\u0627\u0639\u0628",
    "\u0644\u0627\u0639\u0628\u064a\u0646",
    "\u0645\u062f\u0631\u0628",
    "\u0646\u0627\u062f\u064a",
    "\u0627\u0644\u062f\u0648\u0631\u064a",
    "\u0627\u0644\u0628\u0637\u0648\u0644\u0629",
    "\u0647\u062f\u0641",
    "\u0623\u0647\u062f\u0627\u0641",
    "\u0627\u0646\u062a\u0642\u0627\u0644",
    "transfert",
    "joueur",
    "matchs",
    "coupe du monde",
    "\u00e9quipe",
    "equipe",
)


def clean_channel_name(channel: str) -> str:
    return channel.strip().lstrip("@")


def parse_channels() -> list[str]:
    channels = [clean_channel_name(CHANNEL_USERNAME)]
    channels.extend(
        clean_channel_name(channel)
        for channel in ADDITIONAL_CHANNELS.split(",")
        if channel.strip()
    )

    unique_channels: list[str] = []
    for channel in channels:
        if channel and channel not in unique_channels:
            unique_channels.append(channel)
    return unique_channels


def parse_source_names() -> dict[str, str]:
    sources: dict[str, str] = {}
    for pair in CHANNEL_SOURCE_NAMES.split(","):
        if "=" not in pair:
            continue
        channel, source = pair.split("=", 1)
        channel = clean_channel_name(channel)
        source = source.strip()
        if channel and source:
            sources[channel] = source
    sources.setdefault(clean_channel_name(CHANNEL_USERNAME), SOURCE_NAME)
    return sources


CHANNEL_USERNAMES = parse_channels()
SOURCE_BY_CHANNEL = parse_source_names()


def validate_config() -> None:
    if API_ID <= 0:
        raise RuntimeError("API_ID is missing.")
    if not API_HASH:
        raise RuntimeError("API_HASH is missing.")
    if not BACKEND_NEWS_ENDPOINT:
        raise RuntimeError("BACKEND_NEWS_ENDPOINT is missing.")
    if LATEST_POST_LIMIT <= 0:
        raise RuntimeError("LATEST_POST_LIMIT must be greater than 0.")
    if not CHANNEL_USERNAMES:
        raise RuntimeError("At least one Telegram channel is required.")


def iso_date(message_date) -> str:
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=timezone.utc)
    return message_date.astimezone(timezone.utc).isoformat()


def clean_caption(text: str) -> str:
    text = text.replace("\u200f", "").replace("\u200e", "")
    text = re.sub(r"[*_`~]+", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_matching(text: str) -> str:
    text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
    return text.lower()


def post_fingerprint(text: str) -> str:
    normalized = normalize_for_matching(text)
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[^\w\u0600-\u06ff]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:360]


def is_sports_related(text: str) -> bool:
    lower_text = normalize_for_matching(text)
    return any(keyword in lower_text for keyword in SPORT_KEYWORDS)


def image_payload(image_path: str) -> tuple[str | None, str | None]:
    path = Path(image_path)
    if not path.exists():
        return None, None

    content_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return encoded, content_type


def backend_post_id(channel: str, message_id: int) -> int:
    primary_channel = clean_channel_name(CHANNEL_USERNAME)
    if channel == primary_channel:
        return message_id

    channel_hash = zlib.crc32(channel.encode("utf-8")) % 100_000
    return channel_hash * 10_000_000 + message_id


def source_name(channel: str) -> str:
    return SOURCE_BY_CHANNEL.get(channel, channel)


def latest_news_endpoint() -> str:
    if BACKEND_NEWS_ENDPOINT.endswith("/api/news/telegram"):
        return BACKEND_NEWS_ENDPOINT.replace(
            "/api/news/telegram",
            "/api/news/latest?limit=80",
        )
    return BACKEND_NEWS_ENDPOINT.rstrip("/") + "/latest?limit=80"


async def load_existing_fingerprints() -> None:
    http_request = request.Request(latest_news_endpoint(), method="GET")
    try:
        response = await asyncio.to_thread(request.urlopen, http_request, timeout=20)
        payload = json.loads(response.read().decode("utf-8"))
        for item in payload:
            caption = clean_caption(str(item.get("caption", "")))
            if caption:
                seen_post_fingerprints.add(post_fingerprint(caption))
        logger.info("Loaded %s existing backend news fingerprints", len(seen_post_fingerprints))
    except Exception:
        logger.exception("Could not preload backend news fingerprints; continuing")


async def send_to_backend(message, channel: str, image_path: str, caption: str) -> bool:
    encoded_image, content_type = image_payload(image_path)
    post_id = backend_post_id(channel, message.id)
    payload = {
        "telegramPostId": post_id,
        "caption": caption,
        "imagePath": image_path,
        "publishedAt": iso_date(message.date),
        "source": source_name(channel),
        "imageBase64": encoded_image,
        "imageContentType": content_type,
    }
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        BACKEND_NEWS_ENDPOINT,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        await asyncio.to_thread(request.urlopen, http_request, timeout=30)
        logger.info("Sent @%s post %s to backend as %s", channel, message.id, post_id)
        return True
    except error.HTTPError as exc:
        if exc.code == 409:
            logger.info("@%s post %s already exists in backend", channel, message.id)
            return False
        logger.exception("Backend rejected @%s post %s with HTTP %s", channel, message.id, exc.code)
    except Exception:
        logger.exception("Failed sending @%s post %s to backend", channel, message.id)

    return False


async def process_message(message, channel: str) -> None:
    if not message.photo:
        return
    post_key = (channel, message.id)
    if post_key in processed_post_ids:
        return

    processed_post_ids.add(post_key)
    caption = clean_caption(message.raw_text or message.text or "")
    if not caption:
        logger.info("Skipping @%s post %s because it has no caption", channel, message.id)
        return
    if not is_sports_related(caption):
        logger.info("Skipping @%s post %s because it is not sports-related", channel, message.id)
        return

    fingerprint = post_fingerprint(caption)
    if fingerprint in seen_post_fingerprints:
        logger.info("Skipping @%s post %s because matching content already exists", channel, message.id)
        return
    seen_post_fingerprints.add(fingerprint)

    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        image_path = await message.download_media(file=str(DOWNLOADS_DIR))
        if not image_path:
            logger.warning("@%s post %s has no downloadable image", channel, message.id)
            return

        logger.info("Downloaded @%s post %s image: %s", channel, message.id, image_path)
        await send_to_backend(message, channel, str(Path(image_path).resolve()), caption)
    except Exception:
        logger.exception("Failed processing @%s post %s", channel, message.id)


async def get_latest_posts(channel: str) -> None:
    logger.info(
        "Fetching latest %s posts from @%s (%s)",
        LATEST_POST_LIMIT,
        channel,
        source_name(channel),
    )
    messages = await client.get_messages(channel, limit=LATEST_POST_LIMIT)

    for message in reversed(messages):
        await process_message(message, channel)


@client.on(events.NewMessage(chats=CHANNEL_USERNAMES))
async def new_post_handler(event) -> None:
    chat = await event.get_chat()
    channel = clean_channel_name(getattr(chat, "username", "") or str(event.chat_id))
    logger.info("New Telegram post received from @%s: %s", channel, event.message.id)
    await process_message(event.message, channel)


async def main() -> None:
    validate_config()
    if STRING_SESSION:
        logger.info("Using STRING_SESSION for Telegram authentication")
    logger.info("Configured Telegram channels: %s", ", ".join(f"@{name}" for name in CHANNEL_USERNAMES))
    await load_existing_fingerprints()
    for channel in CHANNEL_USERNAMES:
        await get_latest_posts(channel)
    if RUN_ONCE:
        logger.info("RUN_ONCE enabled; exiting after latest-post sync")
        return
    logger.info("Listening for new posts from %s", ", ".join(f"@{name}" for name in CHANNEL_USERNAMES))


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
        if not RUN_ONCE:
            client.run_until_disconnected()
