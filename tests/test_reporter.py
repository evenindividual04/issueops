from app.models.schemas import IssueMetadata
from app.services.reporter import BoardItem, Reporter


def _meta(**overrides) -> IssueMetadata:
    defaults = dict(
        has_reproduction_steps=True,
        has_stacktrace=False,
        has_logs=False,
        is_crash=False,
        is_security_issue=False,
        is_blocker=False,
        operating_system=None,
        environment="prod",
        summary="contributor-friendly task",
        difficulty="easy",
        required_skills=["python"],
        primary_area="documentation",
        verification_hint=None,
        extraction_confidence=0.9,
    )
    defaults.update(overrides)
    return IssueMetadata(**defaults)


def _items():
    return [
        BoardItem(
            number=42,
            title="Fix typo in README",
            url="https://github.com/x/y/issues/42",
            updated_at="2026-05-24T12:00:00Z",
            metadata=_meta(),
        )
    ]


def test_generate_board_writes_html(tmp_path):
    out = tmp_path / "board.html"
    path = Reporter().generate_board(_items(), output_path=str(out), site_url="https://example.com")
    assert out.exists()
    contents = out.read_text()
    assert "Fix typo in README" in contents
    assert path.endswith("board.html")


def test_generate_feed_writes_xml(tmp_path):
    out = tmp_path / "feed.xml"
    path = Reporter().generate_feed(_items(), output_path=str(out), site_url="https://example.com")
    assert out.exists()
    contents = out.read_text()
    assert "Fix typo in README" in contents
    assert path.endswith("feed.xml")
