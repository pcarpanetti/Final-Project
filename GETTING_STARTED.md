# Getting started with RiskWatch

RiskWatch runs in your web browser. You don't need the terminal, and it takes about five minutes.

## What you need

- **Python 3.10 or newer.** If you don't have it, install it from [python.org/downloads](https://www.python.org/downloads/).
  On Windows, tick **Add python.exe to PATH** during setup.
- **Nothing else for the offline demo.** To use a real AI model, you need one of these:
  - Claude Code signed in on this computer, which needs no key
  - An API key from a provider such as Anthropic, OpenAI, Kimi or OpenRouter
  - A local model through Ollama

## 1. Start it

**Windows:** double-click **`start.bat`**.

**Mac or Linux:** open a terminal in this folder and run `sh start.sh`.

The first time, it installs what it needs, which takes a minute or two. Your browser then opens at
`http://127.0.0.1:8765/`. Keep the small black window open while you use the app. Close it when you're done.

If Windows shows a blue SmartScreen warning, choose **More info**, then **Run anyway**.

## 2. Connect a model

1. Enter your name. It is recorded on every approval you make.
2. Choose how the agents get their model:

| Choice | What to enter |
|---|---|
| **Claude login** | Nothing, if Claude Code is signed in. Otherwise click **Sign in with Claude**. Calls count against your Claude plan |
| **A provider** (Anthropic, OpenAI, Kimi, OpenRouter, DeepSeek, Qwen, Mistral, Groq) | Your API key and a model. The address is filled in, and **Load models** can list the models |
| **Ollama** | The model name. Ollama must be running on this computer |
| **Other address** | The address, key and model of any compatible endpoint |
| **Offline demo** | Nothing. This is rule-based code rather than AI, for seeing the workflow free of charge |

3. Click **Test connection**, then **Save and continue**.

Your key stays on this computer. It is held in memory, and it is saved to disk only if you tick the box to remember it.

## 3. Run the workflow

1. Choose a period. **Crash month** is a good first run.
2. Choose who approves. **I will review them** shows you the full process. **Approve automatically** is the
   fastest way to a full output.
3. Click **Start run**.

You can watch progress, and **Stop** then **Resume** carries on without repeating anything.

| Period | Offline demo | Real model, roughly |
|---|---|---|
| Quick look (5 days) | 10 seconds | 6 minutes, 25 calls |
| Crash month (19 days) | 40 seconds | 25 minutes, 95 calls |
| First half of 2020 | 4 minutes | 2.5 hours, 600 calls |
| Full year | 9 minutes | 5 hours, 1,250 calls |

Start small with a real model, because long runs use a lot of your plan or budget.

## 4. Approve

The **Approve** step lists every memo that needs a person: any limit breach, data override or new warning. For each one,
read the memo, then choose:

- **Approve** to release it.
- **Request changes** to send your note back to the agents, after which the memo returns to you.
- **Reject** to stop it. Nothing is published, but the facts stay on record.

**Approve all** clears the list in one go. Your name is recorded on each item. You can do this while the run is still
going, because later days don't wait for you.

## 5. Get the results

- **Dashboard:** the latest position, how VaR held up, limits, the breach register and escalations.
- **Reports:** every memo, breach notice, restatement and monthly review.
- **Download full output (ZIP):** everything released, a summary, and the full audit tables.
- **Run inspector:** for any day, its stages, the 13 automated checks, data decisions and what each agent said.

## Optional: test a change

**Improve** replays the full year to test a proposed change against the fixed baseline, under rules written before any
test ran. Each evaluation takes about 4 minutes and uses no model calls. Changes here affect only your workspace.

## If something goes wrong

| Problem | What to do |
|---|---|
| "Python was not found" | Install Python and tick **Add python.exe to PATH**, then try again |
| The browser did not open | Go to `http://127.0.0.1:8765/` yourself |
| Port already in use | Close the other RiskWatch window. Or, in a terminal, run `python launch.py --port 8800` |
| **Test connection** fails | The message gives the reason. Usually the key, the model name or the address is wrong |
| Claude login says not installed | Use an API key, or the offline demo |
| A memo says "Degraded" or has "Open reviewer concerns" | This is by design: the agents could not finish normally, so a person must look closely |
| You want a clean slate | **Run**, then **Start over**. Old results move to an archive folder |
| Install errors on Windows | Move the project to a short path such as `C:\rw`, because very long paths can fail |

Results are stored in `runtime/web/` inside this folder.

## For the technically minded

Everything in the app also works from the terminal. See [README.md](README.md).
