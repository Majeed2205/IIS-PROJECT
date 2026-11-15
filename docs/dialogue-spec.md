# Dialogue specification

Draft v0.1. Written before any dialogue code, so the rules can be reviewed and changed first.

## What a booking needs

Three details: **service**, **day** and **time**. A booking is only attempted when all three point to one slot in the calendar.

## Rules applied after every caller turn

The rules live in code, not in the language model. The model only turns the caller's words into a structured request.

1. **A detail is missing.** Ask for that detail only. Keep everything already understood.
2. **A detail is ambiguous.** It matches more than one free slot, for example "after five". What happens next depends on the repair strategy below.
3. **All three details match one free slot.** Book it, or read it back first, depending on the strategy.
4. **Nothing free matches.** Decline: say so plainly, offer at most two nearby free slots, and hand control back to the caller.
5. **The caller corrects something.** Change that detail only, keep the rest, and check the calendar again.

## Three repair strategies (switchable)

These are the three approaches compared in the Assignment 1 literature review.

| Strategy | On an ambiguous detail | Before booking |
|---|---|---|
| `repeat` | Asks the caller to say the whole request again | Books without reading back |
| `clarify` | Offers the free slots that match and asks which one | Books without reading back |
| `summarise` | Takes the earliest matching slot | Reads back service, day and time, and waits for yes or no |

## Limits that always apply

- Offer at most three spoken options in one turn. A caller cannot review speech the way they can scan a screen.
- Every slot offered must come from the calendar.
- The final status sentence is built from the booking function's result, never from the model's wording.
- A repeated request must not create a second booking.

## The four repair turns, with example wording

| Turn | When | Example |
|---|---|---|
| Clarify | Ambiguous detail | "On Friday after five I have 5:30 or 6:15. Which would you like?" |
| Confirm | Before booking, in `summarise` | "So that's a haircut on Friday at 5:30 pm. Is that right?" |
| Correct | Caller changes one detail | "Thursday instead. I have 10 am or 2 pm on Thursday. Which would you like?" |
| Decline | Nothing free, or outside what the salon offers | "I have nothing free on Saturday afternoon. I can offer Monday at 11 am or 4 pm, or you can name another day." |

## Test phrases

Each phrase is run against the demo calendar in `data/calendar.json`.

| # | Caller says | Situation | Expected behaviour |
|---|---|---|---|
| 1 | "A haircut on Friday at half five" | Complete, slot free | `summarise` reads back first; the others book. Status comes from the booking result |
| 2 | "Can I come in on Friday after five?" | Service missing, time ambiguous | Ask for the service only, then handle the time by strategy |
| 3 | "A haircut on Friday after five" | Time matches 5:30 and 6:15 | `clarify` offers both; `repeat` asks again; `summarise` reads back 5:30 |
| 4 | "A haircut on Friday at seven" | Slot exists but is taken | Decline that slot and offer 5:30 or 6:15 |
| 5 | "Colour on Saturday afternoon" | Nothing free | Decline, offer another day, hand control back |
| 6 | "A massage on Monday at eleven" | Service not offered | Decline and name the services offered |
| 7 | "Sunday at ten for a haircut" | Salon has no Sunday slots | Decline and ask for another day |
| 8 | "Sometime next week" | Too vague | Ask for a day only |
| 9 | "No, I said Thursday" (after a read-back) | Correction | Change the day only, keep service, re-check the calendar |
| 10 | "Yes" (after a read-back) | Confirmation | Book, then report the status from the booking result |
| 11 | "Book it" (said twice) | Repeated request | No second booking; say it is already booked |

## Not yet specified

- The planted-error switch: which detail is misheard, and how often.
- What is logged for each turn.
- How long the assistant waits before treating silence as a turn.
