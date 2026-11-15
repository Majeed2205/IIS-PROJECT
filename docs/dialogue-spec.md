# Dialogue specification

Draft v0.3. Written before any dialogue code, so the rules can be reviewed and changed first. v0.2 settled six gaps found while planning the repair policy, and v0.3 adds one rule found while building it ("decline early"); each decision and its source is listed under "Decisions" below.

## What a booking needs

Three details: **service**, **day** and **time**. A booking is only attempted when all three point to one slot in the calendar.

## Rules applied after every caller turn

The rules live in code, not in the language model. The model only turns the caller's words into a structured request.

1. **A detail is missing.** Ask for that detail only. Keep everything already understood. When more than one is missing, ask in this order: **day, then service, then time**.
2. **A detail is ambiguous.** It matches more than one free slot, for example "after five". What happens next depends on the repair strategy below.
3. **All three details match one free slot.** Book it, or read it back first, depending on the strategy.
4. **Nothing free matches.** Decline: say so plainly, offer at most two nearby free slots, and hand control back to the caller ("or you can name another day"). A **nearby** slot is one of the two free slots closest in time on the same day; if that day has none, the first two free slots on the next day that has any, counting forward through the week and wrapping round to Monday.
   **Decline early:** this rule is checked as soon as it can be, before asking for a missing service or time. If the service is not offered, decline straight away, even if the day is still missing. If the day (and time, if given) already rule out every free slot, decline straight away instead of first asking for the service.
5. **The caller corrects something.** Change that detail only, keep the rest, and check the calendar again.
6. **The caller says a plain "no" to a read-back**, without saying what is wrong. Ask: "Which part should I change: the service, the day or the time?"

## Three repair strategies (switchable)

These are the three approaches compared in the Assignment 1 literature review.

| Strategy | On an ambiguous detail | Before booking |
|---|---|---|
| `repeat` | Asks the caller to say the whole request again. After **two** repeats that are still ambiguous, stops and hands over: "I'm sorry, I couldn't find one time that fits. I'll ask a member of staff to call you back." (The handover is simulated: no call-back happens.) | Books without reading back |
| `clarify` | Offers the free slots that match and asks which one | Books without reading back |
| `summarise` | Takes the earliest matching slot | Reads back service, day and time, and waits for yes or no |

## Time words

| Caller says | Means |
|---|---|
| "morning" | before 12:00 |
| "afternoon" | 12:00 to 16:59 |
| "evening" | 17:00 onwards |
| "after five" | 17:00 onwards |

## Limits that always apply

- Offer at most three spoken options in one turn. A caller cannot review speech the way they can scan a screen. When more than three slots match, offer the **earliest three**.
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
| 3 | "A haircut on Friday after five" | Time matches 5:30 and 6:15 | `clarify` offers both; `repeat` asks again, and hands over after two still-ambiguous repeats; `summarise` reads back 5:30 |
| 4 | "A haircut on Friday at seven" | Slot exists but is taken | Decline that slot and offer 5:30 or 6:15 |
| 5 | "Colour on Saturday afternoon" | Nothing free | Decline, offer Monday at 11 am or 4 pm, hand control back |
| 6 | "A massage on Monday at eleven" | Service not offered | Decline and name the services offered |
| 7 | "Sunday at ten for a haircut" | Salon has no Sunday slots | Decline, offer Monday at 11 am or 4 pm, and ask for another day |
| 8 | "Sometime next week" | Too vague | Ask for a day only |
| 9 | "No, I said Thursday" (after a read-back) | Correction | Change the day only, keep service, re-check the calendar |
| 10 | "Yes" (after a read-back) | Confirmation | Book, then report the status from the booking result |
| 11 | "Book it" (said twice) | Repeated request | No second booking; say it is already booked |
| 12 | "No" (after a read-back) | Plain rejection | Ask which part to change: the service, the day or the time |
| 13 | "Can I come in on Sunday?" | Service missing, nothing free that day | Decline straight away and offer Monday at 11 am or 4 pm; do not ask for the service first |

## Decisions

| Gap | Decision | Why |
|---|---|---|
| `repeat` could loop forever on the same ambiguous request | Hand over after two still-ambiguous repeats | Keeps `repeat` a pure strategy so the comparison stays fair; Ashktorab et al. (2019) found handover is preferred when repair fails |
| Order of questions when several details are missing | Day, then service, then time | The only order that fits test phrases 2 and 8 as written |
| What "nearby" means when declining | Closest free times on the same day, else the next day with free slots | Offering options ranked highest in Ashktorab et al. (2019); the caller keeps control by naming another day |
| What "morning", "afternoon" and "evening" mean | See "Time words" | Matches "after five" meaning 17:00 onwards |
| More than three matching slots | Offer the earliest three | Spoken options must be held in memory (Week 2 lecture, cognitive load) |
| A plain "no" to a read-back | Ask which part to change | The study measures whether callers notice and correct errors, so correcting must be easy; Ashktorab et al. (2019) found explanations help users correct problems |
| v0.3: when a detail is missing but nothing can match anyway | Decline early (see rule 4) | Asking for details that cannot lead to a booking is a needless turn; Følstad, Law and van As (2024) found later breakdowns damage trust more, so bad news should come as early as possible |

## Not yet specified

- The planted-error switch: which detail is misheard, and how often.
- What is logged for each turn.
- How long the assistant waits before treating silence as a turn.
