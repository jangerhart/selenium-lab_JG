from typer.testing import CliRunner

from epubbook.cli import app


def test_translate_is_an_explicit_subcommand() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "translate" in result.stdout


def test_translate_accepts_documented_arguments() -> None:
    result = CliRunner().invoke(
        app,
        [
            "translate",
            "missing.epub",
            "--output",
            "translated.epub",
            "--yes",
        ],
    )
    assert result.exit_code == 1
    assert "unexpected extra argument" not in result.stdout.lower()
    assert "EPUB nelze otevřít" in result.stdout
