from pytest import CaptureFixture

from lms_project_1 import main


def test_main_prints_greeting(capsys: CaptureFixture[str]) -> None:
    main()

    assert capsys.readouterr().out == "Hello from lms-project-1!\n"
