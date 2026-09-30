# BiteTrace: presentation notes

## One-line pitch
Fifteen people get sick from one cart. Nobody connects them. BiteTrace does.

## Slide flow
1. **Problem.** Street-food illness is invisible because victims are scattered and unconnected. Add your sourced statistic here.
2. **Idea.** Anonymous "I got sick" reports, clustered per stall, automatically escalated.
3. **Live demo (90 seconds).** Open map, tap a stall, report, then Demo tools: simulate 6 people, watch level jump to OUTBREAK, AI verdict, email arrives in the demo FSSAI inbox.
4. **How it decides.** Poisson tail test plus coherent meal window, then AI second opinion.
5. **Anti-abuse (the slide judges remember).** See below.
6. **Architecture.** Static CDN frontend, FastAPI, Postgres, Resend, Gemini, all on free tiers.
7. **Quality.** 151 tests, 98% coverage, ruff clean, CI on every push, secrets in env only.
8. **Limits and next steps.** Calibrated baselines, authority dashboard, multilingual reporting.

## Anti-spam and fake-alert precautions (for the PPT)
1. **One person, one vote.** Device id hashed with a secret salt; one vote per stall; 3 reports per device per week.
2. **Network limits.** Many reports from one network are capped, down-weighted and can never form an outbreak alone.
3. **Trust weighting.** New devices and bursts count less than established, spread-out reporters.
4. **Plausibility checks.** Onset must be 1 to 72 h after eating; a stomach symptom is required; the location must be inside the service area.
5. **Statistics, not counts.** A rival cannot win by volume; significance and exposure-time coherence are required.
6. **AI can only say no.** The AI reviewer sees numbers only (no names, no free text, so no prompt injection) and can hold a report back but never force one out.
7. **Throttled email.** One report per stall per 24 h unless things get worse.
8. **Privacy by design.** No accounts, no names, no phone numbers; IPs stored as hashes; public times blurred to 15 minutes.
9. **Neutral wording.** Reports say "cluster of reports needs inspection", so the authority, not the app, judges.
10. **Bot friction.** Hidden honeypot field and a minimum form-fill time.
11. **Verified accounts.** Optional Google sign-in: one account is one vote across every device it owns.
12. **Secure engineering.** Parameterised SQL, escaped HTML, CSP headers, no secrets in code.

## The demo email question
Two separate inboxes: the **sender** is Resend (a service that delivers mail for BiteTrace, using `onboarding@resend.dev`), and the **receiver** is a Gmail account your team creates to play the role of FSSAI. Nothing ever goes to a real authority.

## Likely viva questions
- **Can someone fake an outbreak?** They would need 5 distinct devices on different networks, spread across accounts' limits, with coherent meal times, passing a Poisson test and the AI reviewer. Each layer raises the cost; we do not claim it is impossible.
- **Why not just count reports?** A popular stall gets more meals, so raw counts mislead; a statistical test against a baseline handles noise.
- **Why an AI at all?** Rules are rigid. The AI is a bounded second opinion over aggregate evidence, and it is one-directional so it cannot raise false alarms.
- **What if the AI is down?** A rules-based reviewer takes over; nothing breaks.
- **Privacy?** No personal data collected; hashed identifiers only.
- **Is this diagnosis?** No. It flags clusters for human inspection.
- **How does it scale?** Static assets on a CDN, stateless serverless API, Postgres for state.
- **What did you not test?** Live Vercel, Resend and Gemini calls need real keys; everything else is covered by tests with fakes.
