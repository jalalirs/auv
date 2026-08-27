# Coral City blueprint

This is the maintained system vision and execution roadmap for the Red Sea
robotic digital twin project. The roadmap is deliberately stored with the code:
completed work changes phase only when its acceptance gate passes and evidence
is preserved.

Program content and milestone status live in `app/plan-data.ts`. The website is
the human-readable view of that source of truth.

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
