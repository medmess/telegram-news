import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
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
processed_post_ids: set[int] = set()

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


def validate_config() -> None:
    if API_ID <= 0:
        raise RuntimeError("API_ID is missing.")
    if not API_HASH:
        raise RuntimeError("API_HASH is missing.")
    if not BACKEND_NEWS_ENDPOINT:
        raise RuntimeError("BACKEND_NEWS_ENDPOINT is missing.")
    if LATEST_POST_LIMIT <= 0:
        raise RuntimeError("LATEST_POST_LIMIT must be greater than 0.")


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


async def send_to_backend(message, image_path: str, caption: str) -> bool:
    encoded_image, content_type = image_payload(image_path)
    payload = {
        "telegramPostId": message.id,
        "caption": caption,
        "imagePath": image_path,
        "publishedAt": iso_date(message.date),
        "source": SOURCE_NAME,
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
        logger.info("Sent Telegram post %s to backend", message.id)
        return True
    except error.HTTPError as exc:
        if exc.code == 409:
            logger.info("Telegram post %s already exists in backend", message.id)
            return False
        logger.exception("Backend rejected post %s with HTTP %s", message.id, exc.code)
    except Exception:
        logger.exception("Failed sending Telegram post %s to backend", message.id)

    return False


async def process_message(message) -> None:
    if not message.photo:
        return
    if message.id in processed_post_ids:
        return

    processed_post_ids.add(message.id)
    caption = clean_caption(message.raw_text or message.text or "")
    if not caption:
        logger.info("Skipping Telegram post %s because it has no caption", message.id)
        return
    if not is_sports_related(caption):
        logger.info("Skipping Telegram post %s because it is not sports-related", message.id)
        return

    try:
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        image_path = await message.download_media(file=str(DOWNLOADS_DIR))
        if not image_path:
            logger.warning("Telegram post %s has no downloadable image", message.id)
            return

        logger.info("Downloaded post %s image: %s", message.id, image_path)
        await send_to_backend(message, str(Path(image_path).resolve()), caption)
    except Exception:
        logger.exception("Failed processing Telegram post %s", message.id)


async def get_latest_posts() -> None:
    logger.info(
        "Fetching latest %s posts from @%s",
        LATEST_POST_LIMIT,
        CHANNEL_USERNAME,
    )
    messages = await client.get_messages(CHANNEL_USERNAME, limit=LATEST_POST_LIMIT)

    for message in reversed(messages):
        await process_message(message)


@client.on(events.NewMessage(chats=CHANNEL_USERNAME))
async def new_post_handler(event) -> None:
    logger.info("New Telegram post received: %s", event.message.id)
    await process_message(event.message)


async def main() -> None:
    validate_config()
    if STRING_SESSION:
        logger.info("Using STRING_SESSION for Telegram authentication")
    await get_latest_posts()
    if RUN_ONCE:
        logger.info("RUN_ONCE enabled; exiting after latest-post sync")
        return
    logger.info("Listening for new posts from @%s", CHANNEL_USERNAME)


if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
        if not RUN_ONCE:
            client.run_until_disconnected()
