# IIS-PROJECT

## Project status

| Part | Where | Status |
|---|---|---|
| Mock calendar (one demo week, fictional salon) | `assistant/slots.py`, `data/calendar.json` | Implemented (step 1) |
| Booking function and status sentence | `assistant/booking.py` | Implemented (step 1) |
| Repair policy (`repeat`, `clarify`, `summarise`) | `assistant/policy.py` | Implemented (step 2) |
| Handover to staff after two failed repeats, or three turns not understood | `assistant/policy.py`, `assistant/chat.py` | Simulated: the assistant says staff will call back; no call happens |
| Conversation loop (typed input in the terminal) | `assistant/chat.py` | Implemented (step 3) |
| Understanding step: Claude Haiku 5.5 turns the caller's words into details | `assistant/model.py` | Implemented (step 4). Live calls need an API key; without one it replays saved answers. If the model leaves out a detail of a turn the keyword reader fully understands, the keyword reader fills it in, and it reads a turn that is only a time ("10") when the model is unsure. A "?" turn that does not ask for something ("You said Friday?"), or a question like "OK, is that right", is not understood, whatever the model read (rule 7) |
| Saved model answers for replay mode | `data/replays.json`, made by `assistant/record.py` | Implemented; the file appears once the answers are recorded with a key |
| Keyword reader for typed input | `assistant/understand.py` | Simulated: used for a sentence with no saved answer when there is no key, or when a live call fails (a [model] message is printed). Also fills in a detail the model left out (see above) |
| Planted-error switch: mishears one time on purpose, to show which strategy catches it | `assistant/mishear.py`, `assistant/chat.py` | Simulated (step 5): off unless `--mishear` is given. One exact time per call is heard as the nearest other free time that day ("half five" on Friday as 6:15 pm); the spec says when it waits |
| Turn logging | | Planned (step 6) |
| Voice in the browser, standing in for a phone line | | Planned (step 7), simulated |

## How to run

```
python -m unittest -v
python -m assistant.demo
python -m assistant.chat clarify      # or repeat / summarise
python -m assistant.chat summarise --mishear   # with the planted-error switch on
```

The tests and the chat need no key and nothing installed: without a key the
assistant runs in replay mode. To use the live model:

```
pip install -r requirements.txt       # the anthropic package, the one agreed dependency
cp .env.example .env                  # then put your own key after ANTHROPIC_API_KEY=
python -m assistant.record            # saves the model's answers in data/replays.json
```
