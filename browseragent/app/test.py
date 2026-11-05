import subprocess

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = r"D:\BroserUse\User Data"

subprocess.Popen([
    chrome,
    f"--user-data-dir={profile}",
    "--profile-directory=Profile 1",
])