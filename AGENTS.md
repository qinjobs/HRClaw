# AGENTS.md

You are Codex working on HRClaw.

HRClaw is a real production codebase. Do not vibe-code. Make small, verified, reversible changes.

## Operating Principles

- Prefer simple code.
- Prefer boring solutions.
- Prefer deleting complexity over adding abstraction.
- Do not introduce dependencies unless clearly justified.
- Do not rewrite large areas unless explicitly asked.
- Do not change unrelated files.
- Do not weaken security, validation, permissions, or tests.
- Use existing project patterns before inventing new ones.

## Before Coding

First understand the task.

Always state:

1. What the user wants
2. What files/modules are likely affected
3. Assumptions
4. A short implementation plan
5. How you will verify it

If the request is ambiguous, ask focused questions. If you must proceed, make the smallest safe assumption and say it.

## Development Loop

Use this loop:

1. Read relevant code
2. Find existing patterns
3. Write or update a test when practical
4. Make the smallest change
5. Run focused checks
6. Summarize what changed and what was verified

## Testing

For bug fixes and business logic:

- Add a regression test when practical.
- Never delete or weaken tests just to pass.
- Prefer behavior tests over implementation-detail tests.
- If tests cannot be run, explain why and provide the exact command that should be run.

## HRClaw Domain Rules

- Use domain language from `CONTEXT.md` if present.
- If a new stable domain concept appears, suggest updating `CONTEXT.md`.
- Keep business rules explicit and testable.
- Keep authorization and data-access checks close to the operation they protect.
- Do not log sensitive user, employee, HR, legal, payroll, or compliance-related data.

## Architecture

Keep boundaries clean:

- UI should not own business rules.
- API/transport code should not hide domain decisions.
- Persistence code should not decide user-facing behavior.
- Shared utilities should stay small and genuinely reusable.

If a task reveals architecture debt, do not refactor everything. Suggest a separate small follow-up.

## Git / PR Hygiene

Before finishing, report:

- Files changed
- Tests run
- Checks run
- Known risks
- Follow-ups

Use this final format:

```text
Summary:
- ...

Verification:
- ...

Risks:
- ...

Follow-ups:
- ...