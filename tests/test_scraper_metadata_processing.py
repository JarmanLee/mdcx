from pathlib import Path
from types import SimpleNamespace

import pytest

from mdcx.config.enums import FixedScrapingType
from mdcx.core.media_resource import MediaResourceContext
from mdcx.core.scraper import _should_process_metadata
from mdcx.models.enums import FileMode
from mdcx.models.flags import Flags
from mdcx.models.types import CrawlersResult, FileInfo, OtherInfo, ScrapeResult


def _shared_scrape_result() -> ScrapeResult:
    return ScrapeResult(FileInfo.empty(), CrawlersResult.empty(), OtherInfo.empty())


@pytest.mark.parametrize(
    ("pre_data", "is_nfo_existed", "update_nfo", "expected"),
    [
        pytest.param(None, False, False, True, id="fresh-scrape-without-nfo-output"),
        pytest.param(None, False, True, True, id="fresh-scrape-with-nfo-output"),
        pytest.param(None, True, False, False, id="existing-nfo-with-update-disabled"),
        pytest.param(None, True, True, True, id="existing-nfo-with-update-enabled"),
        pytest.param(_shared_scrape_result(), False, False, False, id="already-processed-shared-data"),
    ],
)
def test_should_process_metadata(
    pre_data: ScrapeResult | None,
    is_nfo_existed: bool,
    update_nfo: bool,
    expected: bool,
) -> None:
    assert (
        _should_process_metadata(
            pre_data,
            is_nfo_existed=is_nfo_existed,
            update_nfo=update_nfo,
        )
        is expected
    )


@pytest.mark.asyncio
async def test_fresh_scrape_translates_with_no_download_files(monkeypatch: pytest.MonkeyPatch) -> None:
    from mdcx.core import scraper as scraper_module

    class MetadataProcessed(Exception): ...

    result = CrawlersResult.empty()
    result.number = "ABC-123"
    result.title = "日本語タイトル"

    file_info = FileInfo.empty()
    file_info.number = result.number
    file_info.file_path = Path("ABC-123.mp4")
    file_info.folder_path = Path(".")
    file_info.file_name = result.number
    file_info.file_ex = ".mp4"

    class FakeFileScraper:
        def __init__(self, *_args, **_kwargs): ...

        async def run(self, *_args, **_kwargs):
            return result

    async def fake_check_file(*_args, **_kwargs):
        return True

    translated_titles: list[str] = []

    async def fake_translate_title_outline(data, *_args, **_kwargs):
        translated_titles.append(data.title)
        data.title = "中文标题"

    async def fake_translate_actor(*_args, **_kwargs): ...

    async def stop_after_metadata(*_args, **_kwargs):
        raise MetadataProcessed

    Flags.reset()
    monkeypatch.setattr(scraper_module.manager.config, "main_mode", 1)
    monkeypatch.setattr(scraper_module.manager.config, "read_mode", [])
    monkeypatch.setattr(scraper_module.manager.config, "download_files", [])
    monkeypatch.setattr(scraper_module.manager.config, "keep_files", [])
    monkeypatch.setattr(scraper_module.manager.config, "file_size", "0")
    monkeypatch.setattr(scraper_module, "check_file", fake_check_file)
    monkeypatch.setattr(
        scraper_module,
        "get_movie_path_setting",
        lambda *_args, **_kwargs: SimpleNamespace(success_folder=Path("."), movie_path=Path(".")),
    )
    monkeypatch.setattr(
        scraper_module,
        "classify_scrape_task",
        lambda *_args, **_kwargs: SimpleNamespace(scraping_type=FixedScrapingType.AUTO),
    )
    monkeypatch.setattr(scraper_module, "FileScraper", FakeFileScraper)
    monkeypatch.setattr(scraper_module, "show_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scraper_module, "deal_some_field", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scraper_module, "replace_special_word", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scraper_module, "translate_title_outline", fake_translate_title_outline)
    monkeypatch.setattr(scraper_module, "translate_actor", fake_translate_actor)
    monkeypatch.setattr(scraper_module, "translate_info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scraper_module, "replace_word", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scraper_module, "get_video_size", stop_after_metadata)

    media_context = MediaResourceContext()
    try:
        with pytest.raises(MetadataProcessed):
            await scraper_module.Scraper(object())._process_one_file_with_context(
                file_info,
                FileMode.Default,
                media_context,
            )
    finally:
        media_context.close()
        Flags.reset()

    assert translated_titles == ["日本語タイトル"]
    assert result.title == "中文标题"
