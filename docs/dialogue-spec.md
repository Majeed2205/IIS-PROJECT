# Dialogue specification

Draft v0.12. The first version was written before any dialogue code, so the rules could be reviewed and changed first. v0.2 settled six gaps found while planning the repair policy, v0.3 added one rule found while building it ("decline early"), v0.4 added rule 7 for turns the assistant does not understand, found while building the conversation loop, v0.5 made "after X" leave X out, v0.6 added a handover when the assistant keeps not understanding and wrote down rules 8 to 10, which the conversation loop already followed, v0.7 said how rules 6 and 7 treat a change of mind or a turn-down, found while checking the model's answers, and v0.8 said what happens when the caller takes the offered day after a decline and how a mistyped service is handled, both found while trying the assistant in the terminal, added "You said Friday?" to rule 7's questions, and let the keyword reader read a turn that is only a time when the model is unsure. v0.9 specified the planted-error switch for step 5, and v0.10 stopped three replies that went round in circles and made sure a turn that is not understood is not counted as a repeat. v0.11 specified the turn log for step 6, and v0.12 the voice version for step 7. Each decision and its source is listed under "Decisions" below.

## What a booking needs

Three details: **service**, **day** and **time**. A booking is only attempted when all three point to one slot in the calendar.

## Rules applied after every caller turn

The rules live in code, not in the language model. The model only turns the caller's words into a structured request.

1. **A detail is missing.** Ask for that detail only. Keep everything already understood. When more than one is missing, ask in this order: **day, then service, then time**.
2. **A detail is ambiguous.** It matches more than one free slot, for example "after five". What happens next depends on the repair strategy below.
3. **All three details match one free slot.** Book it, or read it back first, depending on the strategy.
4. **Nothing free matches.** Decline: say so plainly, offer at most two nearby free slots, and hand control back to the caller ("or you can name another day"). A **nearby** slot is one of the two free slots closest in time on the same day; if that day has none, the first two free slots on the next day that has any, counting forward through the week and wrapping round to Monday.
   **Decline early:** this rule is checked as soon as it can be, before asking for a missing service or time. If the service is not offered, decline straight away, even if the day is still missing. If the day (and time, if given) already rule out every free slot, decline straight away instead of first asking for the service.
   **After a decline:** if the caller takes the offered day without a time ("Thursday"), and the time they asked for before is not free that day, the assistant forgets that time, so rule 1 asks for what is still missing instead of declining again. A time that is free that day is kept. The offered slots can still be picked (rule 8) when the assistant asks for the time on that day.
5. **The caller corrects something.** Change that detail only, keep the rest (except a time forgotten after a decline, see rule 4), and check the calendar again.
6. **The caller says a plain "no" to a read-back**, without saying what is wrong. Ask: "Which part should I change: the service, the day or the time?" If the "no" names a part ("No, wrong time"), ask for that part again instead; if it gives a new detail ("No, I said Thursday"), it is a correction (rule 5). If it comes with words the assistant does not understand, ask the question too, because the assistant cannot tell what is wrong: after a read-back, "5:30, no wait, 6:15" and "I can't do Monday" both get it. A "no" here means any "no" word: "no", "nope", "nah", "not", "never", "nothing", "none", "wrong", "incorrect", "cannot", or a word ending in "n't" such as "can't" or "isn't", with or without the apostrophe. A "no" that only names what is right ("No, Friday's fine" after a read-back for Friday) is a plain "no" too. After the question, a turn that names no part and gives no detail (a plain "No", a "Yes", or one that is not understood), or a "no" that changes nothing ("No, Friday's fine" again), gets the question again, with "Sorry, I didn't catch that." first if it was not understood, and counts towards the three turns of rule 7.
7. **The assistant does not understand a turn.** This covers a word it does not know, a question about something ("is that Friday?", "You said Friday?"), a "no" that is not an answer to a read-back, two different values for one detail ("Monday and Tuesday"), a change of mind within one turn ("5:30, no wait, 6:15"), turning something down ("I'm busy at 5:30", "I can't do Monday"), or a number it cannot place as a time ("Monday 11"). The assistant changes nothing, says "Sorry, I didn't catch that." and repeats its last question. Under `repeat`, the normal ask-again question is used instead, and the turn is not counted as one of the repeats. After **three** turns in a row that are not understood, it hands over instead: "I'm sorry, I'm having trouble understanding. I'll ask a member of staff to call you back." (simulated, as in `repeat`). Any understood turn starts the count again. After a read-back, a turn like this with a "no" word in it gets the rule 6 question instead, without "Sorry", but it still counts towards the three.
8. **The caller picks an offered slot.** They can name its time ("6:15") or say "the first one", "the second one" or "the third one". A pick that names a different day does not count. If a time is said as well ("the first one after six"), the time decides. When only one slot was offered, a yes takes it, unless it names another day or a time. A pick by place when nothing was offered, or one with a higher number than the slots offered ("the third one" after two), is left out; if nothing else was said, the turn is not understood (rule 7).
9. **The caller answers a read-back with yes.** A plain "yes", or a yes that starts with yes and repeats the details ("Yes, 5:30 is fine"), books. A yes that changes a detail ("yes, after six") is a correction (rule 5). Agreeing with only one detail ("Friday's fine") is not a yes, so the read-back is said again.
10. **One booking per call.** After a booking, "yes" or "book it" again gets the "already booked" sentence from the booking result. Anything else gets "You're all booked. Thank you for calling."

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
| "after five" | later than 17:00 (5 pm itself is left out) |
| "before five" | earlier than 17:00 (5 pm itself is left out) |

## Limits that always apply

- Offer at most three spoken options in one turn. A caller cannot review speech the way they can scan a screen. When more than three slots match, offer the **earliest three**.
- Every slot offered must come from the calendar.
- The final status sentence is built from the booking function's result, never from the model's wording.
- A repeated request must not create a second booking.

## The four repair turns, with example wording

| Turn | When | Example |
|---|---|---|
| Clarify | Ambiguous detail | "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?" |
| Confirm | Before booking, in `summarise` | "So that's a haircut on Friday at 5:30 pm. Is that right?" |
| Correct | Caller changes one detail ("No, I said Thursday") | The changed request is checked again, so the reply can be a question, an offer, a read-back, a booking or a decline, for example: "I have nothing free on Thursday at 5:30 pm. I can offer Thursday at 10 am or 2 pm, or you can name another day." |
| Decline | Nothing free, or outside what the salon offers | "I have nothing free on Saturday afternoon. I can offer Monday at 11 am or 4 pm, or you can name another day." |

## Planted-error switch (simulated)

When the switch is on, the assistant mishears one time on purpose, so the study can see which strategy catches the mistake. The first exact time in a turn the assistant understands is heard as the nearest other free time on the same day (the day said in that turn, or the one already known); on a tie, the earlier one. "A haircut on Friday at half five" is heard as Friday at 6:15 pm. A time is left as it is if no day is known yet, if that day has no other free time, or if the turn answers a read-back ("Yes, 6:15"), and the switch waits for the next exact time. So `summarise` never books a misheard time it has not read back. Only one time per call is misheard: every later time, including a correction, is heard as said. A range ("after five") and a pick by place ("the first one") are never changed. The switch is off unless it is turned on, and works the same under all three strategies and with both readers.

## Turn log

When the log is switched on, the assistant writes one record per caller turn, so the study can count turns, repairs and misses for each strategy. A record holds: the call and turn number, the seconds since the call started, the strategy and whether the planted-error switch is on; what the caller said; which reader read it (a saved model answer, the live model or the keyword reader) and what it read, before any planted error; the planted error, if this turn's time was misheard; what the policy decided (the action, with its slot or offered slots), if it was asked this turn; what the booking returned, if a booking was tried; the reply; the count of turns in a row that got nowhere (rules 6 and 7); and whether the call has ended. Each call goes to its own file in `logs/`, one record per line, written as soon as the turn is answered. The log is off unless it is switched on, because the records hold what the caller typed, and `logs/` is never committed.

## Voice (simulated)

The voice version stands in for a phone line, in a web page on the same computer. The caller presses Talk and speaks; the browser's own speech recognition turns it into text, which is one caller turn, read and answered exactly like a typed turn. The browser decides when the caller has stopped. Silence is never a turn: if nothing is heard, nothing is sent and the caller presses Talk again, so silence cannot use up the handover of rules 6 and 7. The reply is read aloud with one of the computer's own voices; the page lists the more natural "Premium" and "Enhanced" voices first, uses one when the computer has one, and says how to download one when it has none. As on a phone call, the conversation is not shown on screen unless the experimenter switches the transcript on. The strategies, the planted-error switch and the turn log work the same way as in the terminal; the log's "said" is what the recogniser heard. A recogniser may leave out the "?" of a spoken question. A question that starts with a question word ("is that Friday", "did you say half five") is still caught by its words (rule 7), but "You said half five" with no "?" is read as a request, so under `repeat` and `clarify` it can book the time the caller only asked about.

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
| 8 | "Sometime next week" | Too vague | Not understood (rule 7): say sorry and ask for a day only |
| 9 | "No, I said Thursday" (after a read-back) | Correction | Change the day only, keep service, re-check the calendar |
| 10 | "Yes" (after a read-back) | Confirmation | Book, then report the status from the booking result |
| 11 | "Book it" (said twice) | Repeated request | No second booking; say it is already booked |
| 12 | "No" (after a read-back) | Plain rejection | Ask which part to change: the service, the day or the time |
| 13 | "Can I come in on Sunday?" | Service missing, nothing free that day | Decline straight away and offer Monday at 11 am or 4 pm; do not ask for the service first |
| 14 | "I'm busy at 5:30" (after being offered 5:30 or 6:15) | Turns an offer down without a "no" word | Not understood (rule 7): book nothing, say sorry and offer the slots again |
| 15 | "I'm busy" (three times in a row) | Repair keeps failing | Say sorry twice, then hand over to staff on the third turn (rule 7); nothing is booked |
| 16 | "Friday's fine" (after the read-back "a haircut on Friday at 5:30 pm") | Agrees with the day only | Not a yes (rule 9): read back again, book nothing |
| 17 | "5:30, no wait, 6:15" (after being offered 5:30 or 6:15) | Changes their mind within one turn | Not understood (rule 7): book nothing, say sorry and offer the slots again |
| 18 | "I can't do Monday" (after the read-back "a haircut on Monday at 11 am") | Turns the read-back down with a "no" word | Treated as a plain "no" (rule 6): ask which part to change, book nothing |
| 19 | "I'm busy at 5:30" (after the read-back "a haircut on Friday at 5:30 pm") | Turns the read-back down without a "no" word | Not understood (rule 7): say sorry, read back again, book nothing |
| 20 | "Thursday" (after "A haircut on Tuesday at 6" is declined and Thursday at 10 am or 2 pm is offered) | Takes the offered day but not the time | Forget 6 pm and ask "What time on Thursday would you like?", under every strategy (rule 4) |
| 21 | "A haircut on Friday at half five", with the planted-error switch on | The time is misheard as 6:15 pm | `summarise` reads back 6:15 pm, and "No, I said half five" gets the 5:30 pm read-back; `repeat` and `clarify` book 6:15 pm, a miss |

## Decisions

| Gap | Decision | Why |
|---|---|---|
| v0.2: `repeat` could loop forever on the same ambiguous request | Hand over after two still-ambiguous repeats | Keeps `repeat` a pure strategy so the comparison stays fair; Ashktorab et al. (2019) found handover is preferred when repair fails |
| v0.2: order of questions when several details are missing | Day, then service, then time | The only order that fits test phrases 2 and 8 as written |
| v0.2: what "nearby" means when declining | Closest free times on the same day, else the next day with free slots | Offering options ranked highest in Ashktorab et al. (2019); the caller keeps control by naming another day |
| v0.2: what "morning", "afternoon" and "evening" mean | See "Time words" | Evening starts at 17:00, the same point where "after five" begins |
| v0.2: more than three matching slots | Offer the earliest three | Spoken options must be held in memory (Week 2 lecture, cognitive load) |
| v0.2: a plain "no" to a read-back | Ask which part to change | The study measures whether callers notice and correct errors, so correcting must be easy; Ashktorab et al. (2019) found explanations help users correct problems |
| v0.3: when a detail is missing but nothing can match anyway | Decline early (see rule 4) | Asking for details that cannot lead to a booking is a needless turn; Følstad, Law and van As (2024) found later breakdowns damage trust more, so bad news should come as early as possible |
| v0.4: when the assistant is unsure what the caller meant | Change nothing, say "Sorry, I didn't catch that." and ask again (rule 7) | A wrong booking (a miss) costs more than an extra question (a false alarm). It turns a possible misunderstanding into a non-understanding, which is the kind of breakdown the recovery strategies in Bohus and Rudnicky (2005) deal with |
| v0.5: whether "after X" includes X | It leaves X out, the same as "before X" | A caller who hears 6:15 offered and answers "after 6:15" wants something later, so booking 6:15 would be a wrong booking (a miss) |
| v0.6: what happens when the assistant keeps not understanding | Hand over after three turns in a row that are not understood | Rule 7 could otherwise repeat forever. Ashktorab et al. (2019) found handover is preferred when repair fails, and it applies the same way to all three strategies, so the comparison stays fair |
| v0.6: "Friday's fine" after a read-back | Not a yes (rule 9) | It agrees with one detail only; under `summarise` the caller must agree with the whole read-back before booking |
| v0.7: a change of mind ("5:30, no wait, 6:15") or a turn-down ("I can't do Monday") | Not understood (rule 7). After a read-back, one with a "no" word gets the rule 6 question instead, and still counts towards the handover | Taking the last time said could book a time the caller has not settled on, and a wrong booking costs more than an extra question (v0.4). After a read-back the caller is rejecting it, so asking which part keeps correcting easy, as for a plain "no" (v0.2), instead of repeating the read-back they just rejected. Counting it keeps the v0.6 handover working, so the call cannot go round in circles |
| v0.8: the caller takes the offered day after a decline | Forget a time that is not free that day, and ask for one (rule 4); the offered slots can still be picked | Keeping the time, as rule 5 would, declines again ("nothing free on Thursday at 6 pm") with the same offers, and a decline counts as understood, so the call can go round in circles. A free time is still kept, and a day that was not offered still gets its nearby times. "Thursday, same time" is treated like "Thursday", because neither reader can tell which time "same" means. It is the same for all three strategies, so the comparison stays fair |
| v0.8: a question shown only by a "?" ("You said Friday?") | Not understood (rule 7), unless the turn asks for something ("Can I come in on Sunday?", "Friday at 5:30 please?") | Under `clarify` and `repeat`, reading it as a request booked a slot the caller had only asked about, a wrong booking (v0.4) |
| v0.8: a service that looks like a typing mistake ("bread trim") | Not understood (rule 7), so the last question is asked again (the service question names the services); a service the reader does report is declined like any other (rule 4) | Guessing which service the caller meant ("beard trim") could book the wrong one, and hearing the list lets them spot the typo |
| v0.8: a turn that is only a time ("10") when the model is unsure | The keyword reader reads it; a number starting with 0 ("0", "05:30") stays unclear | The model reads each turn on its own, and in a real recording it was unsure about a bare "10", while the keyword reader reads a time on its own the same way every time. It would read "0" as 12 pm, so that stays with the model |
| v0.9: the planted-error switch (step 5): which detail is misheard, and how often | The first exact time is heard as the nearest other free time that day, once per call | A time misheard this way is still bookable, so `summarise` reads back a wrong time the caller can correct, while `repeat` and `clarify` book it (a miss). In the demo calendar a misheard day mostly lands on a taken or empty day and turns into a decline, which no strategy would need to catch. Once per call makes every run the same, so the comparison stays fair, and lets the caller's correction work |
| v0.10: replies that went round in circles ("No" after the which-part question, "No, Friday's fine" after a read-back, "the first one" with nothing offered), and a turn not understood counted as a repeat | After the which-part question, a turn with no part and no detail gets the question again and counts towards the handover (rule 6); a "no" that only names what is right is a plain "no" (rule 6); a pick with nothing to pick from is left out, and is not understood if nothing else was said (rule 8); a turn that is not understood is not a repeat (rule 7) | Each of the three replies was understood but changed nothing, so the v0.6 handover never came and the call could go round for ever. Counting a turn that is not understood as a repeat handed `repeat` over early, which made it look worse than the other strategies and would bias the comparison |
| v0.11: what is logged for each turn (step 6) | The brief's four parts (what was said, what was read, what the policy decided and what the booking returned), plus the turn number and time, the strategy, the reader, the planted error, the reply, the count and whether the call ended; off unless switched on | The extra fields let the analysis tell which reader read a turn, which turn was misheard and how long a call took, which the strategy comparison needs. Logging only when asked means tests and quick tries leave no files, and a participant's words are kept only on purpose, with their consent |
| v0.12: how speech is handled (step 7), and how long silence waits | The browser's own speech recognition and the computer's voices; a Talk button for each turn; silence is never a turn; the text is hidden unless the experimenter switches it on | No install, no key and no new dependency, and the Premium voices sound natural and run on the computer (Claude only writes text, so it cannot be the voice). A Talk button keeps the assistant from hearing itself and makes every run the same, and silence would otherwise use up the handover. Hiding the text keeps the phone-call condition the study is about: a summary has to be heard, not read. Chrome sends the audio to Google to recognise it, so study calls use made-up details |

## Not yet specified

- An understood turn that changes nothing outside the which-part question (a "yes" to an offer, "Friday's fine" said again) does not count towards the handover, so it can be repeated for ever.
- By voice, how to catch a question that only its "?" showed ("You said half five").
