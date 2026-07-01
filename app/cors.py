DEFAULT_CORS_ORIGINS = (
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "https://dev-ucr-dashboard.m3chok.com",
)


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def build_cors_origins(frontend_url: str | None, frontend_urls: str | None) -> list[str]:
    origins: list[str] = []
    for value in (frontend_url, frontend_urls, *DEFAULT_CORS_ORIGINS):
        if not value:
            continue
        for origin in value.split(","):
            normalized = _normalize_origin(origin)
            if normalized and normalized not in origins:
                origins.append(normalized)
    return origins
