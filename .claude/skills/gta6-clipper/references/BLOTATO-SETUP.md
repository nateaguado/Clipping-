# Connecting Blotato (optional): Claude posts your clips for you

Blotato is a paid service, about **$29 a month**, paid to Blotato (no free trial). Check blotato.com for today's
price, and say it plainly before they sign up. It lets Claude post their clips to TikTok, YouTube Shorts and
Instagram Reels at a time they pick, so a clip goes up minutes after it's made (speed matters in launch week).
**It's optional.** Without it they post the finished clips from `~/Stream Clips/finished/` themselves, and that's
completely fine.

How to guide them:
- One step per message. Wait for "done" (or a question) before the next step.
- Use the exact words on buttons, in **bold**. Say where on the screen things are.
- End every step with: "If anything looks different, or you're not sure, send me a screenshot and I'll help."
- Celebrate each finished step. Blotato's website changes now and then; if what they see doesn't match, ask for a
  screenshot and guide them from that, never guess.

## Step 0: Is their Instagram ready?

> First, a quick check on your Instagram clip page (Instagram posting only works with a Creator or Business account, which is free):
> 1. Open the **Instagram** app on your phone and go to your **profile** (your picture, bottom right).
> 2. Tap the **three lines ☰** at the top right.
> 3. Tap **Settings and activity**, then **Account type and tools**.
> 4. If you see **"Switch to personal account"**, you're already set! ✅ Tell me "all set".
>    If you see **"Switch to professional account"**, tap it, choose **Creator**, and follow the screens. It's
>    free and you can switch back any time.
>
> If your screen looks different, send me a screenshot and I'll help.

## Step 1: Make a Blotato account

> 1. On your computer, open your web browser (Chrome, Safari...) and go to **blotato.com**.
> 2. Click the sign-up button and make an account. Using **Continue with Google** is easiest.
> 3. Pick a plan and pay (about $29 a month, paid to Blotato, not to me).
> 4. Tell me "I'm in" when you can see your Blotato dashboard (the main page after you log in).
>
> Stuck anywhere? Send me a screenshot.

They make the account and pay themselves. Never sign up or pay for them.

## Step 2: Connect your clip pages inside Blotato

> 1. In Blotato, find **Settings** (usually in the menu on the left, or under your profile picture).
> 2. Find **Accounts** (it may say "Social accounts").
> 3. Click **TikTok** and log in to your clip page (the page for clips, not your personal one). Then do the same
>    for **YouTube** and **Instagram**. Each one asks you to log in  and click to allow Blotato. That's normal: Blotato
>    needs your OK to post for you. (Your passwords go to TikTok, YouTube and Instagram, not to me.)
> 4. Tell me "connected" when your pages show in your list of accounts.
>
> If a page asks you something I didn't mention, send me a screenshot.

## Step 3: Get your Blotato key (this is the "API key")

> Now I need your Blotato key. It's a long code that lets me use your Blotato for you, a bit like a password, so
> we'll keep it private and won't put it in this chat.
> 1. In Blotato **Settings**, find the part called **API** (it may say **API Key**).
> 2. If there's a button like **Generate API key** or **Create key**, click it.
> 3. Click **Copy** next to the key (or select the whole code and hold **Command ⌘** + tap **C**; on Windows
>    **Ctrl** + **C**).
> 4. Tell me "copied", and I'll open a private notes page for you to paste it into.
>
> Can't find it? Send me a screenshot of your Blotato Settings page.

Then follow SKILL.md → "Private information": open `~/Stream Clips/paste-here.txt`, walk them through paste,
save, close, "done". Read the key, check it looks like one (a long string with no spaces; trim spaces and line
breaks), then go on. If the file is empty, they probably didn't save: walk them through **Command ⌘ + S** again.

## Step 4: Connect it (you do this; they just wait)

> Got it! I'm connecting your Blotato to me now. This takes a few seconds. You might see an **Allow** box: that's
> me saving the connection in my settings. Click **Allow**.

Run exactly this, so the key is read straight from the notes page and never shows up in the Allow box or the chat:
```bash
claude mcp add --transport http blotato https://mcp.blotato.com/mcp --scope user \
  --header "blotato-api-key: $(tr -d '[:space:]' < "$HOME/Stream Clips/paste-here.txt")"
```
If `claude` isn't found (some app-only installs), add it to `~/.claude.json` with a short Python script that reads the key from the paste-here file itself (never type
the key into the command): back the file up first
(`~/.claude.json.backup`), then under the top-level `"mcpServers"` (create it if missing) add
`"blotato": {"type": "http", "url": "https://mcp.blotato.com/mcp", "headers": {"blotato-api-key": "KEY"}}` and check
the file still loads as valid JSON. Then delete `paste-here.txt` for good and tell them it's gone.

## Step 5: Restart Claude (they do this)

> Almost done! Claude needs a restart to see the new connection:
> 1. Close Claude completely. On a Mac: click **Claude** in the top menu bar, then **Quit Claude** (or hold
>    **Command ⌘** and tap **Q**). On Windows: close the window with the **X**.
> 2. Open Claude again.
> 3. Come back to this chat (it's in your list of chats on the left) and type **"I'm back"**.
>
> Your clips and everything we did are saved, nothing gets lost. If you can't find this chat, start a new one and
> say "Let's keep clipping GTA 6".

## Step 6: Test it

Call `blotato_list_accounts`. Read the connected accounts back by name ("I can see your Instagram @handle and your
TikTok"). Save the account ids in `~/Stream Clips/channels/me.md`. Testing posts nothing.

> 🎉 Blotato is connected! From now on I can post your clips for you. I'll always show you each post first and
> wait for your OK, unless you tell me you're happy for me to post without asking.

## If something goes wrong (fix it quietly, explain in one sentence)
- **No Blotato tools after the restart:** run `claude mcp list`. If `blotato` is missing or failed, the key was
  probably cut short or had a space: ask them to copy it again (Step 3, notes page) and redo Step 4.
- **"Unauthorized" or "invalid key":** the key changed or was copied wrong. Get a fresh one (Step 3).
- **A page isn't in the account list:** back to Step 2 (and for Instagram, Step 0: Creator or Business account).
- **They want to disconnect:** `claude mcp remove blotato --scope user`. They can also delete the key in Blotato
  Settings → API, and cancel the plan in Blotato.
