from mangum import Mangum

from app.main import handler


def test_lambda_handler_matches_dockerfile_entrypoint():
    assert isinstance(handler, Mangum)
