from app.services.uploads import MAX_FILE_SIZE


def test_upload_limit_is_200_mib() -> None:
    assert MAX_FILE_SIZE == 200 * 1024 * 1024
