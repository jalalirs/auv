# Coral City blueprint

This is the maintained system vision and execution roadmap for the Red Sea
robotic digital twin project. The roadmap is deliberately stored with the code:
completed work changes phase only when its acceptance gate passes and evidence
is preserved.

Program release definitions and status live in `../program/releases.json`.
The website imports that file directly, so the human-readable roadmap cannot
drift from the repository's acceptance gates. Supporting display content lives
in `app/plan-data.ts`.

The candidate scientific engines and their adoption state live in
`../models/registry.yaml`. They enter the system only through the shared model
adapter and Environment Package boundary described in `../models/README.md`.

## Local development

Use Node.js 22.13 or newer:

```bash
npm install
npm run dev
npm run build
```
