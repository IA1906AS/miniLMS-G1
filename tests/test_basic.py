import pytest

from lms_project_1 import main


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    captured = capsys.readouterr()
    assert "Hello from lms-project-1!" in captured.out
