# Conversational Repair in AI Voice Assistants for Appointment Booking

**IIS-PROJECT**: a booking assistant for a fictional salon, used by typing or by voice in the browser, built for my Intelligent Interactive Systems project. It books one appointment per call and repairs misunderstandings with one of three strategies: `repeat`, `clarify` or `summarise`.

README prose word count: 2220 (rule: words in headings, sentences, bullets and table cells; code blocks, inline code such as commands and file names, and link addresses are not counted).

All seven build steps are done and 264 tests pass. The study with callers that would compare the strategies has not been run, and there is no analysis code yet.

## Project status

| Part | Where | Status |
|---|---|---|
| Mock calendar (one demo week, fictional salon) | `assistant/slots.py`, `data/calendar.json` | Implemented (step 1) |
| Booking function and status sentence | `assistant/booking.py` | Implemented (step 1) |
| Repair policy (`repeat`, `clarify`, `summarise`) | `assistant/policy.py` | Implemented (step 2) |
| Conversation loop (typed input in the terminal) | `assistant/chat.py` | Implemented (step 3) |
| Understanding step: Claude Haiku 5.5 turns the caller's words into details | `assistant/model.py` | Implemented (step 4). Live calls need an API key; without one, saved answers are replayed. See Technology stack |
| Saved model answers for replay mode | `data/replays.json`, made by `assistant/record.py` | Implemented: the 48 answers I recorded are committed. The live chat and voice line do not add to it |
| Keyword reader for typed or spoken turns | `assistant/understand.py` | Simulated: reads a sentence with no saved answer when there is no key or a live call fails; also fills in a detail the model left out |
| Planted-error switch: mishears one time on purpose, to show which strategy catches it | `assistant/mishear.py`, `assistant/chat.py` | Simulated (step 5): off unless `--mishear` is given. One exact time per call is heard as the nearest other free time that day ("half five" on Friday as 6:15 pm) |
| Turn logging: one record per turn, for the study | `assistant/turnlog.py`, `assistant/chat.py` | Implemented (step 6): off unless `--log` is given. One file per call in `logs/` (ignored by git); keep it only with consent |
| Voice in the browser, standing in for a phone line | `assistant/voice.py`, `assistant/voice.html` | Simulated (step 7): a page on this computer. The browser's speech recognition hears the caller and one of the computer's voices reads the reply |
| Handover to staff: after two still-ambiguous repeats (`policy.py`), or three turns in a row that get nowhere (`chat.py`) | `assistant/policy.py`, `assistant/chat.py` | Simulated: the assistant says staff will call back; no call happens |

Not built: the study and its analysis, live telephony, real calendars, payments, undo after a booking, and answers to small talk.

## How to run

Run these from the repository root with Python 3.10 or later. On macOS and Linux the
command is `python3` (on Windows it may be `python` or `py`).

```
python3 -m unittest -v
python3 -m assistant.demo
python3 -m assistant.chat clarify      # or repeat / summarise
python3 -m assistant.chat summarise --mishear   # with the planted-error switch on
python3 -m assistant.chat summarise --log       # writes one record per turn to logs/
python3 -m assistant.voice summarise            # then open http://localhost:8000 in Chrome or Safari
```

The tests and the chat need no key and nothing installed: without a key the
assistant runs in replay mode. If a key is set, start a run with an empty key to force
replay mode: `ANTHROPIC_API_KEY= python3 -m assistant.chat clarify`. To use the live model:

```
python3 -m pip install -r requirements.txt   # the anthropic package, the one agreed dependency
cp .env.example .env                  # then put your own key after ANTHROPIC_API_KEY=
python3 -m assistant.record           # saves the model's answers in data/replays.json
```

In live mode each new sentence the caller says is sent to Anthropic's API, and by voice
Chrome also sends the audio to Google. Only `assistant.record` saves answers; the chat and
the voice line keep a caller's words only in the turn log, when `--log` is on. Use made-up
details in study calls. In a browser that cannot listen (Firefox) the experimenter types each turn instead.

## Technology stack

- **Python 3.10 or later, standard library only.** The tests, the demo, the terminal chat and the voice server (`http.server`, on 127.0.0.1 only) need nothing installed.
- **The `anthropic` package** (`requirements.txt`), only for live calls to the model.
- **Claude Haiku 5.5** (`claude-haiku-5-5`) reads each caller turn for the understanding step.
  - What it does: reads one caller turn on its own and fills in a fixed JSON schema (structured output): service, day, time, a yes or a no, a pick by place, the parts to change, or "unclear". Thinking is turned off, because it is a short reading task and a quick reply matters more.
  - What it does not do: choose the reply (`decide()` and the loop in `chat.py` do), check free times (only `slots.py` does), book, see earlier turns, or speak.
  - Where the keyword reader steps in: if the model leaves out a detail of a turn the keyword reader fully understands, the keyword reader fills it in, and it reads a turn that is only a time ("10") when the model is unsure. A "?" turn that does not ask for something ("You said Friday?"), or a question like "OK, is that right", is not understood, whatever the model read (rule 7).
- **The browser's Web Speech API**: speech recognition turns the caller's speech into text (Chrome sends the audio to Google), and speech synthesis reads each reply with the computer's own voices, Premium and Enhanced voices first.
- **Data**: JSON for the calendar and the saved answers; JSON Lines for the turn logs.
- **Nothing else**: no web framework, database, JavaScript library or telephony service. The voice page is one HTML file, and the tests run headless, with no browser, key or internet connection.

## Known limitations

- No study has been run and there is no analysis code, so there are no results.
- Replay mode is not live behaviour. A sentence with no saved answer goes to the keyword reader, and in my voice test the live model marked a bare "ok" and "correct" unclear, while the keyword reader reads them as a yes.
- The model reads each turn on its own; only the conversation loop keeps the state of the call.
- A spoken question loses its "?". "You said half five" is read as a request by both readers, so under `repeat` and `clarify` it can book the time the caller only asked about.
- An understood turn that changes nothing (a "yes" to an offer) does not count towards the handover, so it can repeat for ever.
- Small talk ("hello how are you") is not understood, because the replies are scripted. There is no undo after a booking.
- Privacy: Chrome sends the audio to Google (Safari was not checked), and in live mode each new sentence goes to Anthropic.
- The three-option limit is shown only by the tests: no day in the demo calendar has more than three free slots.
- The voice line was tried in one test session, by me, and not across accents.

### Choices still undecided

- How to catch a spoken question with no "?", and what to do with an understood turn that changes nothing. The spec lists both as not yet specified.
- Whether small talk should get an answer.
- Whether a bare "ok" or "correct" after a read-back should count as a yes with the live model.
- Which Premium voice to use for study calls.
- The study design: participants, calls per strategy, measures and analysis.

## Development record

I directed Claude Code through the brief's seven build steps. The spec (`docs/dialogue-spec.md`) came before the code and changed only when I decided; its Decisions table gives the reason and source for each change. Before I approved the commit for each build step, independent reviews (an adversary, a reviewer and a judge) and planted-bug tests checked the work. Test counts are after each stage.

### Set-up and step 1: calendar and booking (15 Nov)
- Changed: the initial README, `.gitignore` and `.env.example` ([0e27f6a](https://github.com/Majeed2205/IIS-PROJECT/commit/0e27f6a), [cfad1a6](https://github.com/Majeed2205/IIS-PROJECT/commit/cfad1a6), [acc7522](https://github.com/Majeed2205/IIS-PROJECT/commit/acc7522)); the mock calendar, the booking function and its status sentence, and spec v0.1 ([c24646d](https://github.com/Majeed2205/IIS-PROJECT/commit/c24646d)).
- Why: keys and logs stay out of git, and the spoken status is built from what the booking returned, not from anything a language model says.
- Checked: 11 tests; `.env` and `logs/` have never been committed.

### Step 2: repair policy (15 Nov)
- Changed: spec v0.3 settled the gaps found while planning, such as at most three options and declining early ([1de3282](https://github.com/Majeed2205/IIS-PROJECT/commit/1de3282)); `decide()`, a pure function that never books ([6df124b](https://github.com/Majeed2205/IIS-PROJECT/commit/6df124b)).
- Why: each decision records its reason; most cite the Assignment 1 literature or the Week 2 cognitive-load lecture.
- Checked: 45 tests: spec phrases under all three strategies, every offered slot free, never more than three options.

### Step 3: conversation loop (19 Nov)
- Changed: spec v0.6 ([b21ea03](https://github.com/Majeed2205/IIS-PROJECT/commit/b21ea03)); the loop in `chat.py` and the keyword reader ([2183dd8](https://github.com/Majeed2205/IIS-PROJECT/commit/2183dd8)).
- Why: a wrong booking costs more than an extra question, so a turn that is not fully understood changes nothing and is asked again (rule 7).
- Checked: 117 tests, including replies that must never lead to a booking.

### Step 4: understanding with Claude Haiku 5.5 (20 Nov)
- Changed: `model.py`, replay mode and `record.py`; spec v0.7 ([64579be](https://github.com/Majeed2205/IIS-PROJECT/commit/64579be)).
- Why: my recordings showed the model sometimes drops one detail of a two-part turn ("the first one after six") and books the wrong slot, so the keyword reader fills in the missing detail.
- Checked: 187 tests; every recorded answer checked against the spec; no test calls the API.

### Fixes found by testing (20-21 Nov)
- Changed: "You said Friday?" and "OK, is that right" are no longer read as a request or a yes, by either reader ([6d0f30a](https://github.com/Majeed2205/IIS-PROJECT/commit/6d0f30a), [5e0aceb](https://github.com/Majeed2205/IIS-PROJECT/commit/5e0aceb), [a21f235](https://github.com/Majeed2205/IIS-PROJECT/commit/a21f235)); three replies from my terminal chats, spec v0.8 ([12a89e4](https://github.com/Majeed2205/IIS-PROJECT/commit/12a89e4)).
- Why: these questions booked slots the caller had only asked about, or confirmed a read-back.
- Checked: 212 tests, for questions that must not book and requests that must still work.

### Step 5: planted-error switch (21 Nov)
- Changed: `--mishear`; spec v0.9 ([da7aed0](https://github.com/Majeed2205/IIS-PROJECT/commit/da7aed0)).
- Why: I chose to mishear the time, once per call, because a misheard day mostly lands on a taken day and becomes a decline; once per call keeps every run the same.
- Checked: 227 tests. A review found that an answer to a read-back could be misheard and booked; this was fixed before the commit.

### Fair counting and loops (22 Nov)
- Changed: a turn that is not understood no longer counts as a repeat, and three replies that went round in circles now count towards the handover; spec v0.10 ([cf5e617](https://github.com/Majeed2205/IIS-PROJECT/commit/cf5e617)).
- Why: the old count made `repeat` hand over early, which would bias the comparison.
- Checked: 234 tests; five tests that pinned the old replies were updated.

### Step 6: turn logging (22 Nov)
- Changed: `--log`; spec v0.11 ([bf83ad5](https://github.com/Majeed2205/IIS-PROJECT/commit/bf83ad5)).
- Why: the brief's four parts plus what the study needs (reader, planted error, count, timing); off unless asked for, so a participant's words are kept only with consent.
- Checked: 247 tests, covering every field, the file and the switch.

### Step 7: voice in the browser (23 Nov)
- Changed: `voice.py` and `voice.html`; spec v0.12 ([86fae00](https://github.com/Majeed2205/IIS-PROJECT/commit/86fae00)).
- Why: no install, key or new dependency, and a hidden transcript keeps the phone-call condition.
- Checked: 258 tests.

### Full review (24 Nov)
- Changed: only `record.py` saves model answers; three rule 6 replies are now plain "no"s; the docs and the code agree; spec v0.13 ([1413f54](https://github.com/Majeed2205/IIS-PROJECT/commit/1413f54)).
- Why: after the step 7 commit, my own test voice call showed spoken questions with no "?", times as "10:00 a.m." and one turn heard as "lingo". It also saved my sentences into `data/replays.json`, a file git tracks, which led to the privacy fix. A spec that overstates what is caught would also mislead the report.
- Checked: 264 tests, including that `record.py` still saves.

## AI assistance

- **What I did**: the research question and the design choices are mine. I chose the project, the problem and the literature (Assignment 1); made or approved every design decision in the spec's Decisions table; recorded the model's answers with my own key; tested the terminal chat and the voice line myself and raised the problems I found (stiff replies, small talk, voice quality, that a caller cannot say "?"); and reviewed every commit before it was made from my account.
- **Tool**: Claude Code (Anthropic) in the Claude desktop app, with the model Claude Opus 5.5, used throughout the project.
- **How I directed it**: a project brief (the seven build steps, the scope and what the assessment needs) and my instructions: one step at a time, the spec before the code, every open question brought to me with my answer recorded in the spec's Decisions table, and independent reviews and planted-bug tests before I approved a commit. The brief is not committed.
- **How it helped me**: working to my instructions, it wrote the code and tests and ran the checks and independent reviews. It also helped me write the spec and this README, and helped me prepare the report, the system diagram and the storyboards, which I checked and edited.
- **How results were checked**: the unit tests, planted-bug runs, comparisons with the previous commit, independent reviews and my own runs.
- Claude Haiku 5.5 is part of the system itself (the reader), not a writing aid.

Examples of suggestions I changed, rejected or caught:

1. Prompt changes Claude Code tried for a bare "10" and a mistyped service broke "Monday at 11" in my re-recording, so they were reverted: the keyword reader now reads a bare time, and a mistyped service stays not understood ([12a89e4](https://github.com/Majeed2205/IIS-PROJECT/commit/12a89e4)).
2. I pointed out that a caller cannot say "?" on a phone. I kept the "?" rule for both readers, but the spec now says which spoken questions are caught and lists the rest as not yet specified.
3. I asked whether Claude Haiku could be the voice (it cannot: it only writes text). A paid cloud voice was considered, and I rejected it in favour of the computer's own voices.
4. One of Claude Code's trial runs of the chat (not the unit tests) made an accidental live API call. It was found, the saved answer was removed, and since then its runs of the chat start with an empty key, in replay mode. Later the full review found that live mode saved callers' sentences into a tracked file, and I chose that only `record.py` saves ([1413f54](https://github.com/Majeed2205/IIS-PROJECT/commit/1413f54)).
5. An independent check found that the first version of one question fix made the model path worse, so it was redone before the commit.

## Additional files

- None: there is no ZIP of extra files. Everything needed to run and inspect the work is in this repository.
- The report and its figures are submitted separately.
- Not committed on purpose: `.env` (keys) and `logs/` (callers' words).
