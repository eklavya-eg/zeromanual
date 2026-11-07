import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from contextlib import suppress

from browser_use import Browser

BASE_DIR = Path(__file__).resolve().parents[1]


class SessionBrowsers:
    def __init__(self) -> None:
        self.profiles: dict[str, Path] = {}

    def _profile(self, session_id: str) -> Path:
        root = Path(os.getenv("BROWSER_SESSION_DATA_DIR", str(BASE_DIR / ".sessions")))
        root.mkdir(parents=True, exist_ok=True)
        # browser-use recognizes this prefix and avoids making a second profile copy.
        destination = Path(tempfile.mkdtemp(
            prefix=f"browser-use-user-data-dir-{session_id}-", dir=root,
        ))
        self.profiles[session_id] = destination
        source = Path(os.getenv("BROWSER_USER_DATA_DIR", r"D:\BroserUse\User Data"))
        profile_name = os.getenv("BROWSER_PROFILE_DIRECTORY", "Profile 1")
        profile = Path(profile_name)
        if profile.name != profile_name or profile_name in {".", ".."}:
            raise ValueError("BROWSER_PROFILE_DIRECTORY must be a single directory name")
        if (source / "Local State").is_file():
            shutil.copy2(source / "Local State", destination / "Local State")
        if (source / profile_name).is_dir():
            shutil.copytree(
                source / profile_name,
                destination / profile_name,
                ignore=shutil.ignore_patterns(
                    "Singleton*", "LOCK", "lockfile", "Cache", "Code Cache", "GPUCache",
                    "Service Worker", "Crashpad", "BrowserMetrics*",
                ),
            )
        return destination

    async def create(self, session_id: str) -> Browser:
        browser = None
        try:
            profile_task = asyncio.create_task(asyncio.to_thread(self._profile, session_id))
            try:
                profile = await asyncio.shield(profile_task)
            except asyncio.CancelledError:
                with suppress(Exception):
                    await profile_task
                raise
            browser = Browser(
                executable_path=os.getenv(
                    "BROWSER_EXECUTABLE_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                ),
                user_data_dir=str(profile),
                profile_directory=os.getenv("BROWSER_PROFILE_DIRECTORY", "Profile 1"),
                keep_alive=True,
            )
            await browser.start()
            return browser
        except BaseException:
            await self.destroy(session_id, browser)
            raise

    async def destroy(self, session_id: str, browser: Browser | None) -> None:
        if browser is not None:
            # stop()/close() deliberately leave keep_alive browsers running; kill is explicit.
            await browser.kill()
        profile = self.profiles.get(session_id)
        if profile is not None:
            with suppress(FileNotFoundError):
                await asyncio.to_thread(shutil.rmtree, profile)
            self.profiles.pop(session_id, None)
