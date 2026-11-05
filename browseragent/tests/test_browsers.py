import asyncio
from uuid import uuid4

import pytest

from app import browsers


def test_each_session_uses_an_isolated_profile_and_explicit_kill(monkeypatch, tmp_path):
    seed = tmp_path / "original"
    profile = seed / "Profile 1"
    profile.mkdir(parents=True)
    (seed / "Local State").write_text("{}", encoding="utf-8")
    (profile / "Preferences").write_text("original", encoding="utf-8")
    (profile / "LOCK").write_text("locked", encoding="utf-8")
    monkeypatch.setenv("BROWSER_USER_DATA_DIR", str(seed))
    monkeypatch.setenv("BROWSER_SESSION_DATA_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("BROWSER_PROFILE_DIRECTORY", "Profile 1")

    class FakeBrowser:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.started = False
            self.killed = False

        async def start(self):
            self.started = True

        async def kill(self):
            self.killed = True

    monkeypatch.setattr(browsers, "Browser", FakeBrowser)

    async def scenario():
        factory = browsers.SessionBrowsers()
        one_id, two_id = str(uuid4()), str(uuid4())
        one = await factory.create(one_id)
        two = await factory.create(two_id)
        first_dir = factory.profiles[one_id]
        second_dir = factory.profiles[two_id]
        try:
            assert first_dir != second_dir
            assert one.options["keep_alive"] is True
            assert one.started and two.started
            assert (first_dir / "Profile 1" / "Preferences").read_text() == "original"
            assert not (first_dir / "Profile 1" / "LOCK").exists()
            (first_dir / "Profile 1" / "Preferences").write_text("session-only")
            assert (profile / "Preferences").read_text() == "original"
            assert (second_dir / "Profile 1" / "Preferences").read_text() == "original"
        finally:
            await factory.destroy(one_id, one)
            await factory.destroy(two_id, two)
        assert one.killed and two.killed
        assert not first_dir.exists() and not second_dir.exists()

    asyncio.run(scenario())


def test_browser_start_failure_removes_temporary_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("BROWSER_USER_DATA_DIR", str(tmp_path / "no-seed"))
    monkeypatch.setenv("BROWSER_SESSION_DATA_DIR", str(tmp_path / "sessions"))

    class BrokenBrowser:
        def __init__(self, **kwargs):
            pass

        async def start(self):
            raise RuntimeError("Chrome failed to start")

        async def kill(self):
            pass

    monkeypatch.setattr(browsers, "Browser", BrokenBrowser)

    async def scenario():
        factory = browsers.SessionBrowsers()
        with pytest.raises(RuntimeError, match="Chrome failed"):
            await factory.create(str(uuid4()))
        assert not factory.profiles
        assert not list((tmp_path / "sessions").iterdir())

    asyncio.run(scenario())
