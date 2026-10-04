"""Start the server: `python -m app.serve` (what the Dockerfile runs). Binds to config.HOST (default 127.0.0.1)."""
import uvicorn

from . import config

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, workers=1,
                proxy_headers=True, forwarded_allow_ips=__import__("os").environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"))
