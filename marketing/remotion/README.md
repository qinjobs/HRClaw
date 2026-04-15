# HRClaw Remotion Promo

This directory contains the Remotion project used to assemble the HRClaw product promo video.

## Composition

- `HRClawPromo1080p`
- `1920x1080`
- `30fps`
- `50s`

## Story Flow

1. Brand intro
2. Login and trial hub
3. `jd-scorecard` skill demo
4. Scorecard management
5. Batch resume import and scoring
6. Batch results overview
7. Browser side panel capture
8. CTA outro

## Source Assets

Place the edited product footage in [`public/`](/Users/jobs/Documents/CODEX/ZHAOPIN/marketing/remotion/public):

- `01-login.mp4`
- `02-trial.mp4`
- `03-scorecard.mp4`
- `04-batch-import.mp4`
- `05-batch-results.mp4`
- `06-plugin-sidepanel.mp4`
- `07-hrclaw-skill.mp4`
- `MVP.png`
- `logo.jpg`

## Commands

Install dependencies:

```bash
npm install
```

Start Remotion Studio:

```bash
npm run dev
```

Type-check and lint:

```bash
npm run lint
```

Render the 1080p promo:

```bash
npm run render
```

## Editing Notes

- Main timeline: [`src/PromoVideo.tsx`](/Users/jobs/Documents/CODEX/ZHAOPIN/marketing/remotion/src/PromoVideo.tsx)
- Composition registration: [`src/Root.tsx`](/Users/jobs/Documents/CODEX/ZHAOPIN/marketing/remotion/src/Root.tsx)
- Brand tokens: [`src/theme.ts`](/Users/jobs/Documents/CODEX/ZHAOPIN/marketing/remotion/src/theme.ts)

This promo is intentionally product-first: real interface footage, minimal motion design, and short, recruiter-facing copy.
