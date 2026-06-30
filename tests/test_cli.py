import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "vk_dl_cli", pathlib.Path(__file__).parent.parent / "vk_downloader.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_validate_url_accepts_album():
    assert cli.validate_url("https://vk.com/album-18515186_240802273")
    assert cli.validate_url("https://vk.com/album12345_67890")


def test_validate_url_rejects_garbage():
    assert not cli.validate_url("https://vk.com/video-1_2")
    assert not cli.validate_url("not a url")


def test_main_no_args_returns_error_code():
    assert cli.main([]) == 1


def test_main_bad_url_returns_error_code():
    assert cli.main(["https://vk.com/video-1_2"]) == 1
