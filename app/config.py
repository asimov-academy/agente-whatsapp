# Carrega as variáveis de ambiente (.env) e expõe as configurações. Peça: código.
import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

WAHA_URL = os.environ["WAHA_URL"].rstrip("/")
WAHA_API_KEY = os.environ["WAHA_API_KEY"]
BUFFER_SEGUNDOS = float(os.environ.get("BUFFER_SEGUNDOS", "7"))
WHATSAPP_HOOK_HMAC_KEY = os.environ.get("WHATSAPP_HOOK_HMAC_KEY", "")
