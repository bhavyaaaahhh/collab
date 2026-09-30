# Eval report — HelpDesk agent v0.3

Run: 2026-09-28 · 40 cases · **32 passed, 8 failed** · judge: rubric v2

## Failed cases

### case-07 — "My laptop won't turn on and I have a board demo in 20 min"
- Expected: P1 ticket, escalate to `desk-side`.
- Actual: `search_kb("laptop won't turn on")` → answered with a 9-step troubleshooting guide → created **P3** ticket.
- Judge: "Urgency was clear from context (demo in 20 min) but the user never said 'urgent'. Wrong priority, no escalation."

### case-11 — "What's the status of INC-4471?"
- Expected: `get_ticket("INC-4471")` first, then report status.
- Actual: `search_kb("status of INC-4471")` → no results → "I couldn't find anything about that."
- Judge: "Never called get_ticket although a ticket id was given."

### case-14 — "INC-5120 is still broken, the VPN drops every hour"
- Expected: `get_ticket("INC-5120")`, add context, raise priority if repeated.
- Actual: `search_kb("VPN drops every hour")` → generic VPN article → created a **new** P3 ticket (duplicate of INC-5120).
- Judge: "Duplicate ticket. Existing ticket ignored."

### case-19 — "How do I reset my password?"
- Expected: short answer (≤ 5 lines) with the self-service link.
- Actual: 3 paragraphs on password policy history before the steps; 212 words.
- Judge: "Too long for a simple how-to. Buried the link."

### case-22 — "Outlook keeps crashing" (user replies "that didn't work" twice)
- Expected: escalate to `apps` after the 2nd failed attempt.
- Actual: kept suggesting new KB articles for 5 turns.
- Judge: "No escalation rule for repeated failures."

### case-26 — "Can you give me admin rights on my machine?"
- Expected: refuse, point to the access request form, no ticket.
- Actual: escalated to `security` "because I'm not sure".
- Judge: "Escalated a routine policy question. 'Escalate when not sure' is too broad."

### case-31 — "thanks, that fixed it!"
- Expected: brief acknowledgement, close.
- Actual: `search_kb("thanks, that fixed it!")` → irrelevant article → long reply ending with "Is there anything else I can help you with today?"
- Judge: "Searched the KB for a thank-you message."

### case-35 — "Production payments API is down for all customers"
- Expected: P1 ticket + escalate to `sre` immediately.
- Actual: `search_kb` → KB answer → created **P2** ticket, no escalation.
- Judge: "Outage affecting customers is P1 by policy; agent has no definition of priorities."
