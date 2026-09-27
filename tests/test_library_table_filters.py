from pathlib import Path


def test_library_table_filters_module_exports():
    web = Path(__file__).resolve().parents[1] / "web"
    filters_js = (web / "js" / "library-table-filters.js").read_text(encoding="utf-8")
    table_js = (web / "js" / "library-table.js").read_text(encoding="utf-8")

    for symbol in (
        "applyLibraryFilters",
        "createFiltersSpoiler",
        "createPaginationBar",
        "loadFilters",
        "loadPageSize",
        "paginateItems",
    ):
        assert f"export function {symbol}" in filters_js

    assert 'library-table-filters-${storageKey}' in filters_js or "library-table-filters-" in filters_js
    assert "library-table-page-size-" in filters_js
    assert "library-filters-spoiler" in filters_js
    assert "library-table-footer" in filters_js

    assert "./library-table-filters.js" in table_js
    assert "library-table-shell" in table_js
    assert "mountLibraryTable" in table_js
    assert "tableOptionsByShell" in table_js
    assert "resolveTableOptions" in table_js
    assert "applyLibraryFilters" in table_js
    assert "createPaginationBar" in table_js


def test_transcripts_archive_library_tabs():
    web = Path(__file__).resolve().parents[1] / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    router_js = (web / "js" / "router.js").read_text(encoding="utf-8")
    transcripts_js = (web / "js" / "transcripts.js").read_text(encoding="utf-8")
    archive_js = (web / "js" / "archive.js").read_text(encoding="utf-8")

    for element_id in (
        "transcripts-files-wrap",
        "transcripts-batches-wrap",
        "archive-files-wrap",
        "archive-batches-wrap",
    ):
        assert element_id in html

    assert "transcripts-wrap" not in html
    assert "archive-jobs-wrap" not in html
    assert 'parts[0] === "transcripts"' in router_js
    assert 'parts[0] === "archive"' in router_js
    assert "transcripts-files" in transcripts_js
    assert "transcripts-batches" in transcripts_js
    assert "selectable: true" in transcripts_js
    assert "bulkActions" in transcripts_js
    assert "runJobsBulkAction" in transcripts_js
    assert "selectable: true" in archive_js
    assert "runBatchesBulkAction" in archive_js
    assert "archive-files" in archive_js
    assert "archive-batches" in archive_js
    assert "applyArchiveTabUi" in archive_js


def test_transcripts_archive_no_topbar_search():
    web = Path(__file__).resolve().parents[1] / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    router_js = (web / "js" / "router.js").read_text(encoding="utf-8")
    transcripts_js = (web / "js" / "transcripts.js").read_text(encoding="utf-8")
    archive_js = (web / "js" / "archive.js").read_text(encoding="utf-8")

    assert "transcripts-search" not in html
    assert "archive-search" not in html
    assert "transcripts-search" not in router_js
    assert "searchQuery" not in transcripts_js
    assert "searchQuery" not in archive_js
