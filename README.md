# IIS-PROJECT

## Project status

| Part | Where | Status |
|---|---|---|
| Mock calendar (one demo week, fictional salon) | `assistant/slots.py`, `data/calendar.json` | Implemented (step 1) |
| Booking function and status sentence | `assistant/booking.py` | Implemented (step 1) |
| Repair policy (`repeat`, `clarify`, `summarise`) | `assistant/policy.py` | Implemented (step 2) |
| Handover to staff after two failed repeats | `assistant/policy.py` | Simulated: the assistant says staff will call back; no call happens |
| Conversation loop (typed input) | | Planned (step 3) |
| Understanding step (Claude Haiku 5.5, with a replay mode that needs no key) | | Planned (step 4) |
| Planted-error switch | | Planned (step 5) |
| Turn logging | | Planned (step 6) |
| Voice in the browser, standing in for a phone line | | Planned (step 7), simulated |

## How to run

```
python -m unittest -v
python -m assistant.demo
```
