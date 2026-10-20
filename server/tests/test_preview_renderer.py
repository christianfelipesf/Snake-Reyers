from cobrinha_server.services import preview_renderer


def test_graphical_environment_supplies_x11_defaults(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    env = preview_renderer._graphical_environment()

    assert env["DISPLAY"] == ":0"
    assert env["XDG_RUNTIME_DIR"] == f"/run/user/{preview_renderer.os.getuid()}"
    assert env["XAUTHORITY"]


def test_graphical_environment_preserves_session_values(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":7")
    monkeypatch.setenv("XAUTHORITY", "/tmp/custom-xauthority")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/custom-runtime")

    env = preview_renderer._graphical_environment()

    assert env["DISPLAY"] == ":7"
    assert env["XAUTHORITY"] == "/tmp/custom-xauthority"
    assert env["XDG_RUNTIME_DIR"] == "/tmp/custom-runtime"
