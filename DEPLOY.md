# Deploying CiteLocal — step by step for first-time deployers

This gets you a real web address (like `citelocal-xyz.onrender.com`) that
anyone can open in a browser — no coding, no terminal, just clicking through
a website. Takes about 5 minutes.

## What you need first

- A GitHub account that can see the `Kazakholigarch/millions` repo (you
  likely already have this, since that's where this code lives).
- An email address, for signing up at Render.

## Steps

1. Go to **[render.com](https://render.com)** and sign up (usually via
   "Sign up with GitHub" — simplest option, one click).

2. Once logged in, click **New +** (top right) → **Blueprint**.

3. Connect your GitHub account if it asks, then pick the **`millions`**
   repository.

4. Render will find the `render.yaml` file already sitting in this repo and
   read the settings from it automatically — service name, build command,
   start command, all pre-filled. You shouldn't need to type anything.

5. Confirm the branch is `claude/research-approach-question-6jpgwb`
   (the render.yaml already specifies this, but double-check the dropdown).

6. Click **Apply** / **Create**. Render will build and deploy — takes
   2-4 minutes the first time. You'll see build logs scroll by; that's normal.

7. When it's done, Render shows you a URL like
   `https://citelocal.onrender.com`. **That's your app.** Click it.

8. You'll land on the CiteLocal form. Fill in a real business (try your own
   website, or any local business) and click **Run audit** to confirm it
   works end to end.

## Before you send the link to a prospect

The free tier falls asleep after 15 minutes with no visitors, and takes
30-60 seconds to wake back up on the next request. If you send a cold
prospect a link to a page that takes a minute to load, that's a bad first
impression.

**Fix**: open the link yourself about a minute before you send it, or before
a call/demo. That "wakes" the server, and it'll stay fast for the next
15 minutes of activity.

(If this becomes annoying once you have real customers, Render's paid tier
— a few dollars a month — removes the sleep entirely. Not needed on day one.)

## Turning on the live AI-visibility probe (optional, not required to start)

The core audit (crawler access, structured data, content, citations) works
with zero configuration — that's most of the report's value and it's
already live once you deploy.

The extra "ask ChatGPT/Claude/Perplexity who they'd recommend instead of
you" feature needs an API key. To add it later:

1. In the Render dashboard, open your service → **Environment**.
2. Add one of: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `PERPLEXITY_API_KEY`
   (get one from the corresponding provider's console).
3. Save — Render redeploys automatically with the key available.

Don't block launching on this. Ship without it, add it once you have a
reason to.

## If something goes wrong

- **Build fails**: click into the failed deploy, read the log — it's
  almost always a typo-free `requirements.txt` issue, which this repo's
  isn't, so this should just work. If it doesn't, copy the error and ask.
- **Page loads but "Run audit" errors out**: check the Render **Logs** tab
  for the actual Python error and share it.

## What you now have

A real, working, publicly-accessible tool. Use the free tier while you get
your first customers, upgrade once revenue justifies removing the cold
start.
