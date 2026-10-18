# Daily kids video → YouTube (free, runs on GitHub, nothing to install)

Every day GitHub starts a free cloud computer that: asks Gemini for a topic and script, has Gemini check it is safe for kids, makes the voice (Edge TTS), the images (Pollinations) and the video (FFmpeg), uploads it to YouTube as "made for kids", and remembers the topic so it never repeats.

## Step 1: GitHub repository (3 min, in your browser)
1. Create a free account at github.com.
2. Click **New repository**, name it `kids-videos`, choose **Public** (public repos have unlimited free minutes), click Create.
3. Click **uploading an existing file**, drag in everything from this folder (including the `.github` folder, `music`, `main.py`, `render.py`, `history.json`) and click Commit.
   If the web page will not take the hidden `.github` folder: click **Add file → Create new file**, type the name `.github/workflows/daily.yml` and paste the contents of that file.

## Step 2: Gemini key
Get a free key at https://aistudio.google.com/apikey.

## Step 3: YouTube access (one time, ~10 min, in your browser)
1. https://console.cloud.google.com → create a project → **APIs & Services → Library** → enable **YouTube Data API v3**.
2. **OAuth consent screen**: External, fill the basics, add your Google account as a test user. Then click **Publish app** so the login does not expire after 7 days.
3. **Credentials → Create credentials → OAuth client ID → Web application.** Add this redirect URI: `https://developers.google.com/oauthplayground`. Copy the **Client ID** and **Client secret**.
4. Open https://developers.google.com/oauthplayground
   - Click the gear icon, tick **Use your own OAuth credentials**, paste the Client ID and secret.
   - In the left box type the scope `https://www.googleapis.com/auth/youtube.upload`, click **Authorize APIs** and sign in with the YouTube channel account.
   - Click **Exchange authorization code for tokens** and copy the **Refresh token**.

## Step 4: Add the secrets
In your repo: **Settings → Secrets and variables → Actions → New repository secret**. Add these four, with exactly these names:
`GEMINI_API_KEY`, `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`

## Step 5: Test and forget
1. Go to the **Actions** tab → **Daily kids video** → **Run workflow**. It takes about 5 to 10 minutes.
2. Check YouTube Studio for a private video.
3. After that it runs by itself every day at 08:00 UTC.

## Change settings
Edit `.github/workflows/daily.yml` (pencil icon): `LANGUAGE`, `VOICE` (French: `French` / `fr-FR-DeniseNeural`), `PRIVACY`, `SCENE_COUNT`, and the cron time. Categories are in `main.py`. Put royalty-free `.mp3` files in the `music` folder for background music.

## Good to know
- Videos uploaded through a YouTube API project that has not passed Google's API audit are forced to private. Keep `PRIVACY: private` and make them public in YouTube Studio until you pass the audit.
- If a run fails, GitHub emails you. The usual causes are an expired YouTube token or a free service being down.
- Free services can change their limits: Gemini, Pollinations and Edge TTS. Edge TTS and Pollinations can occasionally block cloud IP addresses; if that happens, tell me the error and I will swap that step.
- Never paste your keys into the files: only into Secrets.
