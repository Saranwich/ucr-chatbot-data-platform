from app.cors import build_cors_origins


def test_dashboard_deploy_origin_allowed_by_default():
    origins = build_cors_origins(None, None)

    assert "https://dev-ucr-dashboard.m3chok.com" in origins


def test_cors_origins_accept_comma_separated_env_and_dedupe():
    origins = build_cors_origins(
        "https://dashboard.example.com/",
        "https://extra.example.com, https://dashboard.example.com",
    )

    assert origins.count("https://dashboard.example.com") == 1
    assert "https://extra.example.com" in origins
