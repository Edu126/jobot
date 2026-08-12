━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 JOBOT — Quick start for Mac
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Jobot helps you search job boards, get AI-scored matches, and generate
tailored resumes + cover letters. Everything runs on your Mac — nothing
gets uploaded anywhere. Your data stays private.


FIRST TIME (only need to do this once):
─────────────────────────────────────────

  ⚠️  IMPORTANT — macOS will block the first double-click with
      "Apple could not verify…"  This is expected and normal.

      Open the file  READ FIRST — macOS security prompt.txt
      for 3 ways to unblock it (60 seconds each).

      TL;DR — the most reliable method:
        System Settings → Privacy & Security →
        scroll to "Install Jobot.command was blocked" →
        click "Open Anyway".

  1. Follow READ FIRST to unblock Install (only once).
  2. Then Terminal opens with the setup wizard.
  3. When it asks for a Gemini API key:
       • Open https://aistudio.google.com in a browser
       • Sign in with any Google account
       • Click "Create API key" → copy it
       • Paste it in the Terminal and press Enter
  4. Wait for "Setup complete!" — then close the Terminal window.


TO USE JOBOT (every time):
───────────────────────────

  1. Double-click:  Start Jobot.command
     (no security prompt this time — Install cleared it for you)
  2. Your browser will open at http://127.0.0.1:8000 automatically.
  3. Use the app.
  4. When you're done, close the Terminal window (Cmd+Q).


WHAT IF SOMETHING BREAKS?
──────────────────────────

  • First check: is the Terminal window still open? If not, launch again.
  • Second: run "Install Jobot.command" again — it's safe, it won't break
    anything, it'll just make sure everything's up-to-date.
  • Third: send me the message that shows in the Terminal so I can help.


WHERE IS MY DATA?
──────────────────

  Everything is inside this folder:
    • data/jobot.db          — your saved jobs, applications, resume history
    • data/jobs_cache/       — cached search results
    • .env                    — your API key (never leaves this Mac)

  If you want to back up, copy the whole folder somewhere safe.
  If you want to start fresh, delete data/jobot.db (loses everything).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
