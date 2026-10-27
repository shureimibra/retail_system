# Open items and plans (27 Oct 2026)

What's built, what's waiting, and where each plan lives.

## Built, waiting for the owner's UAT and merge

Merge in this order: each branch builds on the one before.

| Phase | Branch | UAT rows |
|---|---|---|
| 4: free real channels, UAT fixes | `phase-4/free-channels` | S01–S24 (done) |
| 5: Excel import, shop link, API keys | `phase-5/plug-in` | S25–S27 (S27, the connections, not tested yet) |
| 5b: Log missed sale offline | `phase-5b/offline-capture` | S28–S30 |
| 6: Ask, order suggestions, smart replies | `phase-6/assistant` | S31–S33 |

## Planned, documented, not built

| Item | Plan | Waits for |
|---|---|---|
| Deploying to the Netcup VPS | `docs/deployment.md` | A domain; the day the owner chooses |
| Paid WhatsApp, SMS, email, M-Pesa | `docs/going-live-messaging.md` | Business documents and provider approvals |
| Per-shop WhatsApp numbers and M-Pesa tills | `docs/going-live-messaging.md` §6 | Before the second shop joins |
| A real AI model behind Ask and reply drafts | `docs/ai-assistant-plan.md` | The owner's go-ahead and budget |
| Ready-made POS connectors, outgoing webhooks, website widget | `docs/integrations-plan.md` | What the first shops actually use |

## Next phase: the front door

The marketing website and video. That starts with a design brief and research, including:
- the video tool the owner has seen;
- motion and scroll references.

Every third-party tool or skill gets a **security check before it's installed or run**.
