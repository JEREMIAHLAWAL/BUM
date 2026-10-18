"""Offline ownership regressions through the real Planner contract extractor."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from types import SimpleNamespace
import json
import os
import tempfile
import unittest
from unittest.mock import patch

with patch("dotenv.load_dotenv", return_value=False):
    from orchestrator.contract_tools import extract_contract_from_spec


# Captured verbatim from FinderShip/pipeline/FS-011_PLANNER_READINESS.md,
# starting at the Planner specification (coordinator provenance preface omitted).
# Retained here so this regression also runs in clean/offline checkouts.
READINESS_PLANNER_SPEC = r"""# FS-011 Planner Specification — Authentication & Protected Sessions

## 0. Status, authority, and stewardship

- **Mode:** planning-only. No implementation, tool execution, dependency install, or test/review evidence is claimed or produced by this document. "Model output is not implementation evidence."
- **Checkpoint:** source publication `7fce3d341e8bd007e7c413fb5082923adfe9c3df`; task branch `fs-011/authentication` at `4ee9ff602727e00086f1bb59f4fc2da1d2f92a02`. 15 source hashes verified. `apps/web` auth files do not exist yet. All `packages/shared/**` files are READ ONLY. Supabase-managed `auth.users` only; no business DB schema/migrations.
- **Planner decision — ACCEPT:** I accept **integration/contract stewardship** for this slice. I own `pipeline/spec.md`, handoffs, and `docs/FS-011.md`. Builders must not edit these.
- **No new agent identities.** Roles are distinct stages: Planner (`deepseek-v4.1-flash`), Frontend/Backend (`claude-sonnet-5.5`), Tester (`deepseek-v4.1-flash`), Reviewer (`claude-sonnet-5`). Identities are configuration, not execution evidence.
- **Coordinator (Hermes):** owns dependency integration **only after this contract**, and is the sole writer of `apps/web/package.json`, `pnpm-lock.yaml`, `.env.example`, and root test-script/config integration. Correct package names: `@supabase/ssr`, `@supabase/supabase-js`. Registry lookup returned `@supabase/ssr@0.12.7` and `@supabase/supabase-js@2.118.0`; these are **not installed** and are **not** integration evidence. Coordinator must re-verify current registry + peer graph against Next 16 / React 19 before pinning exact compatible versions.

## 1. Architecture invariants (binding on all stages)

- Next.js App Router 16, React 19, strict TS, alias `@/*` → `./src/*`, Node `>=24 <25`, pnpm `10.9.0`. Next 16 uses `proxy.ts` (not middleware).
- Auth uses a **per-request** `createServerClient` from the official SSR package with awaited Next cookies. `proxy.ts` refreshes cookies only — it is **not** the authorization boundary.
- Every protected server page and every sensitive server action verifies identity **independently** via `getUser()`. Never authorize via `getSession()`, decoded JWT, client flags, `userId`/role/plan input, or a service-role client. No global mutable user/client state.
- **Server-only guards are separate from UI components.** Frontend never imports server-authorization modules into client components.
- Fails closed on missing config/provider outage → bounded `unavailable` outcome, never a fake session.
- Redirect origin from validated canonical config; never from Host/forwarded-host. Reject off-origin, protocol-relative, encoded/backslash redirects. GET logout must not mutate. Auth responses `private, no-store`.
- Password policy/config consistent provider↔UI. Logger must not emit credentials, tokens, or raw provider errors.
- **Frontend must not edit the Backend gate** (`apps/web/src/server/auth/**`, `apps/web/src/app/(protected)/app/page.tsx`). **Backend must not edit** `protected-content.tsx` or UI.
- **Dependencies are NOT installed.** No stage may write import statements that cannot resolve until Coordinator has integrated pins; builders code against the interfaces below and the declared package names.

## 2. FILE BOUNDARIES (exact paths)

### Frontend — create/modify ONLY these

- `apps/web/src/app/(auth)/login/page.tsx`
- `apps/web/src/app/(auth)/register/page.tsx`
- `apps/web/src/app/(auth)/forgot-password/page.tsx`
- `apps/web/src/app/(auth)/reset-password/page.tsx`
- `apps/web/src/components/auth/auth-form-shell.tsx`
- `apps/web/src/components/auth/login-form.tsx`
- `apps/web/src/components/auth/register-form.tsx`
- `apps/web/src/components/auth/forgot-password-form.tsx`
- `apps/web/src/components/auth/reset-password-form.tsx`
- `apps/web/src/components/auth/field-error.tsx`
- `apps/web/src/components/auth/form-status.tsx`
- `apps/web/src/app/(protected)/app/protected-content.tsx`

### Backend — create/modify ONLY these

- `apps/web/src/server/auth/client.ts`
- `apps/web/src/server/auth/session.ts`
- `apps/web/src/server/auth/outcomes.ts`
- `apps/web/src/server/auth/validation.ts`
- `apps/web/src/server/auth/redirects.ts`
- `apps/web/src/server/auth/actions.ts`
- `apps/web/src/server/auth/logout-route.ts` (helper consumed by `apps/web/src/app/auth/logout/route.ts`)
- `apps/web/src/app/auth/logout/route.ts`
- `apps/web/src/app/auth/callback/route.ts`
- `apps/web/src/app/auth/confirm/route.ts`
- `apps/web/src/app/(protected)/app/page.tsx`
- `apps/web/src/proxy.ts`

### Tester — create ONLY these (all inside `apps/web/test`)

- `apps/web/test/auth-register.test.ts`
- `apps/web/test/auth-login.test.ts`
- `apps/web/test/auth-protected-gate.test.ts`
- `apps/web/test/auth-session-refresh.test.ts`
- `apps/web/test/auth-logout.test.ts`
- `apps/web/test/auth-recovery.test.ts`
- `apps/web/test/auth-callback.test.ts`
- `apps/web/test/auth-password-update.test.ts`
- `apps/web/test/auth-csrf-redirect.test.ts`
- `apps/web/test/auth-unavailable.test.ts`
- `apps/web/test/auth-accessibility.test.tsx`
- `apps/web/test/helpers/auth-test-harness.ts` (fixtures/mocks only, not a spec case file)

No globs. Tester may write **only** the above exact filenames.

### Coordinator — create/modify ONLY these

- `apps/web/package.json`, `pnpm-lock.yaml`, `.env.example`, `package.json` (test-script integration to run `apps/web` tests), `apps/web/README.md` (auth setup docs only), bounded test-runner config if strictly required. Coordinator is the **one** lockfile writer.

### Planner — owns

- `pipeline/spec.md`, `docs/FS-011.md`, handoff records.

## 3. EXPORTED SIGNATURES (contract before builders edit)

### `apps/web/src/server/auth/outcomes.ts`

```ts
export type AuthFieldErrors = Record<string, string[]>;
export type AuthFormStatus =
  | 'idle'
  | 'validation_error'
  | 'invalid_credentials'
  | 'confirmation_pending'
  | 'recovery_acknowledged'
  | 'session_expired'
  | 'unavailable'
  | 'success';
export interface AuthFormState {
  status: AuthFormStatus;
  fieldErrors?: AuthFieldErrors;
  formMessage?: string; // safe, non-enumerating copy only
  email?: string; // echo of submitted email for pending/acknowledged
  redirectTo?: string; // fixed same-origin path on success
}
export const initialAuthFormState: AuthFormState;
export function toUnavailable(): AuthFormState;
export function toValidationError(fieldErrors: AuthFieldErrors): AuthFormState;
```

### `apps/web/src/server/auth/client.ts` (server-only — `import 'server-only'`)

```ts
export function createSupabaseServerClient(): Promise<SupabaseClient>; // per-request, awaited cookies
```

### `apps/web/src/server/auth/session.ts` (server-only)

```ts
export type VerifiedUser = { id: string; email: string | null };
export function getVerifiedUser(): Promise<VerifiedUser | null>; // getUser(), never getSession()
export function requireVerifiedUser(): Promise<VerifiedUser>; // throws AuthUnverifiedError
export class AuthUnverifiedError extends Error {}
```

### `apps/web/src/server/auth/validation.ts`

```ts
export const AUTH_EMAIL_MAX = 254;
export const AUTH_PASSWORD_MIN = 8;
export function validateEmail(
  raw: unknown,
): { ok: true; value: string } | { ok: false; message: string };
export function validatePassword(
  raw: unknown,
): { ok: true; value: string } | { ok: false; message: string };
export function validateRegisterForm(formData: FormData): AuthFieldErrors | null; // null == valid
export function validateLoginForm(formData: FormData): AuthFieldErrors | null;
export function validateRecoveryForm(formData: FormData): AuthFieldErrors | null;
export function validatePasswordUpdateForm(formData: FormData): AuthFieldErrors | null;
```

### `apps/web/src/server/auth/redirects.ts`

```ts
export function resolveSameOriginPath(candidate: unknown, fallback: string): string; // rejects off-origin/`//`/`\`/encoded
export function getCanonicalOrigin(): string; // validated config; throws if unset
```

### `apps/web/src/server/auth/actions.ts` (`'use server'`)

```ts
export function registerAction(prev: AuthFormState, formData: FormData): Promise<AuthFormState>;
export function loginAction(prev: AuthFormState, formData: FormData): Promise<AuthFormState>;
export function requestRecoveryAction(
  prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState>;
export function updatePasswordAction(
  prev: AuthFormState,
  formData: FormData,
): Promise<AuthFormState>;
```

No action accepts `userId`/role/plan.

### Route handlers

- `apps/web/src/app/auth/logout/route.ts`: `export async function POST(request: Request): Promise<Response>;` (clears cookies, redirects to fixed `/login`). No `GET` export.
- `apps/web/src/app/auth/callback/route.ts`: `export async function GET(request: Request): Promise<Response>;` (remote-verified token, confirm step).
- `apps/web/src/app/auth/confirm/route.ts`: `export async function POST(request: Request): Promise<Response>;` (explicit confirmation POST to avoid scanner GET consumption).

### Frontend components (client where interactive)

```ts
// auth-form-shell.tsx
export function AuthFormShell(props: {
  title: string;
  description?: string;
  children: React.ReactNode;
}): JSX.Element;
// field-error.tsx
export function FieldError(props: { id: string; messages?: string[] }): JSX.Element | null;
// form-status.tsx
export function FormStatus(props: { state: AuthFormState }): JSX.Element | null; // maps outcomes to safe copy
// login-form.tsx / register-form.tsx / forgot-password-form.tsx / reset-password-form.tsx
export function LoginForm(): JSX.Element;
export function RegisterForm(): JSX.Element;
export function ForgotPasswordForm(): JSX.Element;
export function ResetPasswordForm(): JSX.Element;
// protected-content.tsx — presentation only; receives verified summary as props
export function ProtectedContent(props: { user: { email: string | null } }): JSX.Element;
```

Pages import the corresponding form and render inside `AuthFormShell`. `app/(protected)/app/page.tsx` (Backend) calls `requireVerifiedUser()` and passes the summary to `ProtectedContent`; it must not call `getSession()`.

## 4. PERMITTED TOKENS / libraries

- Styling: **Tailwind v4 utility classes only** (repo has no `src/theme/colors.ts`; do not invent `Colors.*` tokens or a theme module). Semantic HTML + Tailwind is sufficient.
- Forms: React `useActionState` (React 19) + native form actions. No form library.
- Required libraries (Coordinator to pin): `@supabase/ssr`, `@supabase/supabase-js` (server-side only).
- Cookies: `next/headers` `cookies()` (awaited).

## 5. NEGATIVE CONSTRAINTS (prohibited)

- **Forbidden packages:** `date-fns`, `@expo/vector-icons`, any form/state library, any resolver beyond Next/pnpm workspace, any Redis/session-store dependency, any OAuth/social provider SDK.
- **No** `getSession()`-based authorization, decoded JWT trust, client-supplied identity, service-role client in browser/server code, global mutable auth state.
- **No** edits to `packages/shared/**`, migrations, DB/business tables, `IDEA.md`, `docs/FS-011_HANDOFF.md`, `app/layout.tsx`, `app/page.tsx`, `app/globals.css`.
- **No** new files with globs, no test files outside the exact `apps/web/test` list, no Tester production fixes, no self-approval.
- **No** dependency/lockfile/env edits by Frontend/Backend/Tester; Coordinator only, after this contract.
- **No** raw provider error/message, token, password, or account-enumeration leakage; no token-bearing URL reflection/referrers/cache.
- **No** live emails, signup, purchase, deployment, main merge, or FS-012/FS-013/contact work.

## 6. Tester matrix — 14 required cases → exact files

| #   | Case                                                                                              | File                           |
| --- | ------------------------------------------------------------------------------------------------- | ------------------------------ |
| 1   | Valid registration → confirmation pending, no premature auth/paid/trial                           | `auth-register.test.ts`        |
| 2   | Duplicate/unknown → generic non-enumerating outcome                                               | `auth-register.test.ts`        |
| 3   | Valid login → server-verified protected identity                                                  | `auth-login.test.ts`           |
| 4   | Invalid credentials/malformed → bounded error, no success cookie/log                              | `auth-login.test.ts`           |
| 5   | Direct route/sensitive-action bypass denied (anon/forged/expired)                                 | `auth-protected-gate.test.ts`  |
| 6   | User A → B → anon: no user/response/cache/cookie leak                                             | `auth-protected-gate.test.ts`  |
| 7   | Refresh rotates request+response cookies; fail closed                                             | `auth-session-refresh.test.ts` |
| 8   | Logout clears session, subsequent access denied, revocation limits                                | `auth-logout.test.ts`          |
| 9   | Recovery safe ack, unknown equivalence, rate/outage, no live email                                | `auth-recovery.test.ts`        |
| 10  | Callback token-type verify; invalid/expired/replayed/wrong-type; no leak; GET prefetch no consume | `auth-callback.test.ts`        |
| 11  | Password update requires verified session; failures stay errors                                   | `auth-password-update.test.ts` |
| 12  | Cross-origin mutation + redirect attacks denied (exercise framework protections, not regex-only)  | `auth-csrf-redirect.test.ts`   |
| 13  | Missing config/outage → unavailable, no fake user/content                                         | `auth-unavailable.test.ts`     |
| 14  | Phone/desktop/a11y: labels, keyboard/focus, error announcement, autocomplete, pending submit      | `auth-accessibility.test.tsx`  |

Map outcomes to `docs/FS-009.md` AC-A01..A05. Case 14 browser/manual evidence is separate from unit/source checks. Mocks do not establish business RLS/SQL isolation or real auth deliverability.

## 7. Evidence & delivery (later stages; not claimed now)

Required real checks after implementation: frozen install, `pnpm check`, `pnpm run security:audit`, `pnpm run security:files`, tracked drift, independent Review. Preserve `braces@3.0.3` exception expiring **2026-11-17 00:00 UTC**. Record exact versions, commands/exits, test counts, case mapping, findings/fix cycles, mock vs browser vs live limits, changed paths, head SHA, exact-head CI in `docs/FS-011.md`. Draft PR only; founder accepts; never merge main.

## 8. NEEDS CONTEXT

- Real `@supabase/ssr` / `@supabase/supabase-js` exact compatible pins for Next 16 / React 19 are **unconfirmed** — Coordinator must resolve from live registry + peer graph before any import is finalized.
- Confirmed Supabase email-template/confirm mechanism must be re-verified by Backend against current official docs; the fragment-vs-server-confirmation flow is asserted here as design intent, not verified behavior.
- No `apps/web/test` runner/test script exists at baseline; Coordinator owns adding the exact invocation that actually runs the 11 files above.
- `@supabase/ssr`'s real `createServerClient`/cookie-API type surface must be read from the installed package before Backend codes the adapter — no API shapes are invented here.
"""


EXPLOIT_SPEC = (
    "## FILES TO MODIFY\n- tests/test_owned.py\n\n"
    "## NEEDS CONTEXT\n- tests/test_reference.py\n\n"
    "## ACCEPTANCE CRITERIA\n- Preserve reference test read-only."
)


class ContractSectionOwnershipTests(unittest.TestCase):
    def extract(self, spec):
        # Never resolve a default project or its manifest in these regressions.
        return extract_contract_from_spec(spec, manifest=SimpleNamespace(rules=None))

    def test_reference_section_never_grants_writable_ownership(self):
        contract = self.extract(EXPLOIT_SPEC)
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])
        self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    @contextmanager
    def scratch_pipeline(self):
        # Guard dotenv BEFORE every real import. No default repo resolution,
        # authorization mocks, providers, Git or commands are needed here.
        with patch("dotenv.load_dotenv", return_value=False):
            from orchestrator import pipeline, repo_tools
        scratch = Path.home() / "AppData/Local/hermes/cache/scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        manifest = SimpleNamespace(rules=SimpleNamespace(
            test_write_roots=["tests", "apps/web/test"],
            allowed_write_roots=[], prohibited_files=[], forbidden_imports=[],
            forbidden_tokens=[], required_packages=[]))
        with ExitStack() as stack:
            for name in ("TEMP", "TMP", "TMPDIR"):
                stack.enter_context(patch.dict(os.environ, {name: str(scratch)}))
            root = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=scratch)))
            for module in (pipeline, repo_tools):
                stack.enter_context(patch.object(module, "get_repo_root", return_value=root))
                stack.enter_context(patch.object(module, "get_active_manifest", return_value=manifest))
            events = []

            def emit_event(**event):
                events.append(event)
                (root / "events.json").write_text(json.dumps(events), encoding="utf-8")

            stack.enter_context(patch.object(pipeline, "emit_event", side_effect=emit_event))
            yield pipeline, root, manifest, events

    def test_real_extractor_then_real_tester_validator_reject_reference_write_and_delete(self):
        contract = self.extract(EXPLOIT_SPEC)
        with self.scratch_pipeline() as (pipeline, root, _, events):
            pipeline._validate_tester_file_operations(
                [("write", "tests/test_owned.py", "assert True")], contract)
            reference = root / "tests/test_reference.py"
            reference.parent.mkdir()
            reference.write_text("REFERENCE_UNCHANGED\n", encoding="utf-8")
            for action in ("write", "delete"):
                with self.subTest(action=action), self.assertRaisesRegex(
                        PermissionError, "outside writable Planner contract"):
                    pipeline._validate_tester_file_operations(
                        [(action, "tests/test_reference.py", "overwritten")], contract)
                block = ("```write:tests/test_reference.py\noverwritten\n```" if action == "write"
                         else "```delete:tests/test_reference.py\n```")
                with self.assertRaisesRegex(PermissionError, "outside writable Planner contract"):
                    pipeline.parse_and_apply_agent_file_operations(block, "tester", contract=contract)
                self.assertEqual(reference.read_text(encoding="utf-8"), "REFERENCE_UNCHANGED\n")
            self.assertEqual(events, [])
            self.assertFalse((root / "tests/test_owned.py").exists())

    def test_real_extractor_owned_create_update_delete_uses_guarded_helpers(self):
        with self.scratch_pipeline() as (pipeline, root, _, events):
            contract = self.extract(EXPLOIT_SPEC)
            path = "tests/test_owned.py"
            for content, field in (("assert True", "created"), ("assert 1 == 1", "modified")):
                result = pipeline.parse_and_apply_agent_file_operations(
                    f"```write:{path}\n{content}\n```", "tester", contract=contract)
                self.assertEqual(result[field], [path])
                self.assertEqual((root / path).read_text(encoding="utf-8"), content + "\n")
            result = pipeline.parse_and_apply_agent_file_operations(
                f"```delete:{path}\n```", "tester", contract=contract)
            self.assertEqual(result["deleted"], [path])
            self.assertFalse((root / path).exists())
            self.assertTrue(events)
            self.assertEqual(json.loads((root / "events.json").read_text()), events)

    def test_extracted_ownership_does_not_override_manifest_or_real_filesystem_guard(self):
        contract = self.extract("## FILES TO MODIFY\n- tests/test_owned.py\n- src/production.py\n")
        with self.scratch_pipeline() as (pipeline, root, manifest, events):
            for path in ("tests/test_other.py", "src/production.py"):
                with self.subTest(path=path), self.assertRaises(PermissionError):
                    pipeline.parse_and_apply_agent_file_operations(
                        f"```write:{path}\nunsafe\n```", "tester", contract=contract)
            manifest.rules.prohibited_files = ["tests/test_owned.py"]
            with self.assertRaisesRegex(PermissionError, "manifest rule"):
                pipeline.parse_and_apply_agent_file_operations(
                    "```write:tests/test_owned.py\nunsafe\n```", "tester", contract=contract)
            manifest.rules.prohibited_files = []
            manifest.rules.test_write_roots = []
            with self.assertRaisesRegex(PermissionError, "test_write_roots"):
                pipeline._validate_tester_file_operations([("write", "tests/test_owned.py", "")], contract)
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(events, [])

    def test_explicit_conflicting_ownership_is_rejected_in_either_order(self):
        writable = "## FILE BOUNDARIES\n- tests/test_conflict.py\n"
        reference = "## NEEDS CONTEXT\n- tests/test_conflict.py\n"
        for spec in (writable + reference, reference + writable):
            with self.subTest(spec=spec), self.assertRaisesRegex(ValueError, "tests/test_conflict.py"):
                self.extract(spec)

    def test_reference_alias_conflicts_reject_both_orders_and_never_mutate_reference(self):
        canonical = "tests/test_reference.py"
        aliases = ["./tests/test_reference.py", "tests/./test_reference.py",
                   "tests/fixtures/../test_reference.py", "tests//test_reference.py"]
        if os.name == "nt":
            aliases.append("TESTS/TEST_REFERENCE.PY")
        for alias in aliases:
            # Check alias on either side of the conflict, in both section orders.
            for owned, reference in ((canonical, alias), (alias, canonical)):
                writable = f"## FILE BOUNDARIES\n- `{owned}`\n"
                readonly = f"## NEEDS CONTEXT\n- `{reference}`\n"
                for spec in (writable + readonly, readonly + writable):
                    with self.subTest(owned=owned, reference=reference, spec=spec):
                        with self.scratch_pipeline() as (pipeline, root, _, events):
                            target = root / canonical
                            target.parent.mkdir()
                            target.write_text("REFERENCE_UNCHANGED\n", encoding="utf-8")
                            with self.assertRaisesRegex(ValueError, "Conflicting writable/reference"):
                                self.extract(spec)
                            # A rejected contract must never be passed to apply.
                            # Separately prove that the actual extractor's alias-only
                            # read context cannot grant this target through Tester.
                            contract = self.extract(
                                "## FILE BOUNDARIES\n- tests/test_owned.py\n" + readonly)
                            self.assertEqual(contract["reference_files"], [reference])
                            for path in (canonical, alias):
                                for action in ("write", "delete"):
                                    with self.assertRaises(PermissionError):
                                        pipeline._validate_tester_file_operations(
                                            [(action, path, "unsafe")], contract)
                                    block = f"```{action}:{path}\n" + (
                                        "unsafe\n" if action == "write" else "") + "```"
                                    with self.assertRaises(PermissionError):
                                        pipeline.parse_and_apply_agent_file_operations(
                                            block, "tester", contract=contract)
                                    self.assertEqual(target.read_text(encoding="utf-8"), "REFERENCE_UNCHANGED\n")
                            self.assertEqual(events, [])
                            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_alias_identity_comparison_does_not_repair_or_normalize_literal_tokens(self):
        canonical = "tests/test_reference.py"
        alias = "./tests/fixtures/../test_reference.py"
        contract = self.extract(f"## FILE BOUNDARIES\n- `{alias}`\n")
        self.assertEqual(contract["file_boundaries"], [alias])
        for quote in ("`", "'", '"'):
            for malformed in (quote + alias, alias + quote, alias + quote + "/suffix"):
                for heading in ("FILE BOUNDARIES", "NEEDS CONTEXT"):
                    with self.subTest(malformed=malformed, heading=heading):
                        contract = self.extract(
                            f"## FILE BOUNDARIES\n- {canonical}\n## {heading}\n- {malformed}\n")
                        self.assertEqual(contract["file_boundaries"], [canonical])
                        self.assertEqual(contract["reference_files"], [])

    def test_unsupported_path_tokens_are_not_repaired_into_writable_aliases(self):
        contract = self.extract(
            '## FILE BOUNDARIES\n- C:tests/test_drive.py\n'
            '- https://example.invalid/tests/test_url.py\n'
            '- "tests/with space.py"\n- `tests/test_owned.py`\n')
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])

    def test_unmatched_delimiters_never_authorize_truncated_literal_paths(self):
        paths = ["tests/test_alias.py", "apps/web/test/(auth)/[userId]/page.test.tsx"]
        for path in paths:
            for quote in ("`", "'", '"'):
                for token in (path + quote + "/suffix", quote + path, path + quote,
                              quote + path + quote + "/suffix", "prefix" + quote + path + quote):
                    with self.subTest(token=token), self.scratch_pipeline() as (pipeline, root, _, events):
                        contract = self.extract("## FILE BOUNDARIES\n- " + token + "\n")
                        target = root / path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("UNCHANGED\n", encoding="utf-8")
                        # Both the validator and the actual apply path must reject
                        # the manufactured prefix, not merely the malformed input.
                        for action in ("write", "delete"):
                            with self.assertRaises(PermissionError):
                                pipeline._validate_tester_file_operations([(action, path, "unsafe")], contract)
                            with self.assertRaises(PermissionError):
                                pipeline.parse_and_apply_agent_file_operations(
                                    f"```{action}:{path}\n" + ("unsafe\n" if action == "write" else "") + "```",
                                    "tester", contract=contract)
                            self.assertEqual(target.read_text(encoding="utf-8"), "UNCHANGED\n")
                        self.assertEqual(contract["file_boundaries"], [])
                        self.assertEqual(events, [])

    def test_balanced_multiple_literal_paths_preserve_routes_through_real_apply(self):
        paths = ["tests/test_one.py", "tests/test_two.py",
                 "apps/web/test/(auth)/[[...userId]]/page.test.tsx", "tests/test_four.py"]
        contract = self.extract(
            f"## FILE BOUNDARIES\n- `{paths[0]}`, '{paths[1]}'; \"{paths[2]}\" {paths[3]}\n")
        self.assertEqual(contract["file_boundaries"], paths)
        with self.scratch_pipeline() as (pipeline, root, _, _):
            for path in paths:
                result = pipeline.parse_and_apply_agent_file_operations(
                    f"```write:{path}\nfixture\n```", "tester", contract=contract)
                self.assertEqual(result["created"], [path])
                self.assertEqual((root / path).read_text(encoding="utf-8"), "fixture\n")

    def test_dynamic_route_paths_are_exact_and_never_promoted_from_globs(self):
        paths = [
            "apps/web/test/(auth)/[userId]/page.test.tsx",
            "apps/web/test/(docs)/[...slug]/route.test.ts",
            "apps/web/test/(docs)/[[...slug]]/page.test.tsx",
            ".env.example", "pnpm-lock.yaml",
        ]
        contract = self.extract("## FILE BOUNDARIES\n" +
                                "\n".join(f"- `{path}`" for path in paths) +
                                "\n- `tests/*.test.ts`\n- `tests/**/test_unknown.py`\n")
        self.assertEqual(contract["file_boundaries"], paths)

    def test_numbered_markdown_and_route_group_paths(self):
        contract = self.extract(
            "### 2.1 FILE BOUNDARIES (exact paths)\n"
            "- `apps/web/src/app/(auth)/login/page.tsx`\n"
            "### 2.2 NEEDS CONTEXT\n- `src/app/(app)/_layout.tsx`\n"
            "### 2.3 ACCEPTANCE CRITERIA\n- tests/test_not_owned.py\n")
        self.assertEqual(contract["file_boundaries"], ["apps/web/src/app/(auth)/login/page.tsx"])
        self.assertEqual(contract["reference_files"], ["src/app/(app)/_layout.tsx"])

    def test_nested_owner_subsections_preserve_only_the_file_section(self):
        contract = self.extract(
            "## FILE BOUNDARIES\n### Frontend — create/modify ONLY these\n"
            "- src/ui.tsx\n### Backend — create/modify ONLY these\n- src/api.ts\n"
            "### Tester — create ONLY these\n- tests/test_owned.py\n"
            "## EXPORTED SIGNATURES\n### Backend\n- src/not_owned.ts\n"
            "## NEEDS CONTEXT\n- tests/test_reference.py\n")
        self.assertEqual(contract["file_boundaries"], ["src/ui.tsx", "src/api.ts", "tests/test_owned.py"])
        self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    def test_no_crossheading_leakage_even_to_a_deeper_unrelated_heading(self):
        for heading in ("## ACCEPTANCE CRITERIA", "### ACCEPTANCE CRITERIA", "ACCEPTANCE CRITERIA:"):
            with self.subTest(heading=heading):
                contract = self.extract("## FILES TO MODIFY\n- tests/test_owned.py\n" + heading +
                                        "\n- tests/test_unowned.py\n## NEEDS CONTEXT\n"
                                        "- tests/test_reference.py\n## NOTES\n- tests/test_unread.py\n")
                self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])
                self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    def test_inline_mentions_are_not_sections(self):
        contract = self.extract(
            "The FILES TO MODIFY include tests/test_inline.py.\n"
            "- NEEDS CONTEXT: tests/test_inline_reference.py\n"
            "## FILES TO MODIFY examples are not ownership\n- tests/test_example.py\n"
            "## NOTES\n- FILE BOUNDARIES: tests/test_note.py\n")
        self.assertEqual(contract["file_boundaries"], [])
        self.assertEqual(contract["reference_files"], [])

    def test_multiple_conventional_file_sections_and_plain_colon_headings(self):
        contract = self.extract(
            "FILES TO CREATE OR MODIFY:\n- src/first.ts\n"
            "EXPORTED SIGNATURES:\n- `export function first(): void`\n"
            "## FILES TO CHANGE\n- src/second.ts\n"
            "## FILES TO CREATE\n- src/third.ts\n"
            "NEEDS CONTEXT:\n- src/reference.ts\n"
            "NOTES:\n- src/not_owned.ts\n")
        self.assertEqual(contract["file_boundaries"], ["src/first.ts", "src/second.ts", "src/third.ts"])
        self.assertEqual(contract["reference_files"], ["src/reference.ts"])
        self.assertTrue(any("export function first()" in s for s in contract["exported_signatures"]))

    def test_bold_owner_labels_and_protected_subsection(self):
        contract = self.extract(
            "## FILE BOUNDARIES\n**Create (Frontend):**\n- src/new.ts\n"
            "**Modify (Backend — narrow, additive only):**\n- src/existing.ts\n"
            "**Never create, modify, or delete:**\n- src/protected.ts\n"
            "## NEEDS CONTEXT\n- src/protected.ts\n")
        self.assertEqual(contract["file_boundaries"], ["src/new.ts", "src/existing.ts"])
        self.assertEqual(contract["reference_files"], ["src/protected.ts"])

    def test_fenced_examples_cannot_open_an_ownership_section(self):
        contract = self.extract(
            "## NOTES\n```markdown\n## FILES TO MODIFY\n- tests/test_example.py\n```\n"
            "## FILES TO MODIFY\n- tests/test_owned.py\n")
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])

    def test_atx_bold_labels_with_colons_and_closing_hashes(self):
        contract = self.extract(
            "## **2. FILE BOUNDARIES**: ##\n### **Frontend**: ###\n- tests/test_owned.py\n"
            "## **3. REFERENCE FILES**: ##\n- tests/test_reference.py\n## END\n")
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])
        self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    def test_plain_and_bold_role_labels_nest_under_conventional_file_labels(self):
        for opening, owner in (("FILE BOUNDARIES", "Frontend:"),
                               ("FILES TO MODIFY:", "**Backend**"),
                               ("**FILE BOUNDARIES**", "Tester:")):
            with self.subTest(opening=opening, owner=owner):
                contract = self.extract(f"{opening}\n{owner}\n- tests/test_owned.py\n"
                                        "NEEDS CONTEXT\n- tests/test_reference.py\n"
                                        "NOTES\n- tests/test_outside.py\n")
                self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])
                self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    def test_writable_label_inside_reference_subsection_cannot_promote_references(self):
        contract = self.extract(
            "## NEEDS CONTEXT\n### Existing fixtures\n"
            "#### FILE BOUNDARIES\n- tests/test_reference.py\n"
            "## FILE BOUNDARIES\n- tests/test_owned.py\n")
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])
        self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    def test_setext_headings_and_numbered_plain_and_bold_labels(self):
        for writable, reference, stop in (
            ("2. FILE BOUNDARIES\n------------------", "3. NEEDS CONTEXT\n----------------", "4. NOTES\n========"),
            ("2. FILES TO MODIFY:", "3. REFERENCE FILES:", "4. NOTES:"),
            ("**2. FILES TO MODIFY:**", "**3. REFERENCE FILES**:", "**4. NOTES:**"),
        ):
            with self.subTest(writable=writable):
                contract = self.extract(f"{writable}\n- tests/test_owned.py\n{reference}\n"
                                        f"- tests/test_reference.py\n{stop}\n- tests/test_notes.py\n")
                self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])
                self.assertEqual(contract["reference_files"], ["tests/test_reference.py"])

    def test_nested_reference_sections_and_owner_siblings_obey_heading_hierarchy(self):
        contract = self.extract(
            "## FILE BOUNDARIES\n### 2.1 Frontend\n- src/ui.tsx\n"
            "#### 2.1.1 NEEDS CONTEXT\n- src/reference.ts\n"
            "##### Existing fixtures\n- tests/test_reference.py\n"
            "### 2.2 Backend\n- src/api.ts\n"
            "## NOTES\n### Tester\n- tests/test_not_owned.py\n"
            "## REFERENCE FILES\n### Existing fixtures\n- tests/test_other_reference.py\n"
            "## END\n- tests/test_outside.py\n")
        self.assertEqual(contract["file_boundaries"], ["src/ui.tsx", "src/api.ts"])
        self.assertEqual(contract["reference_files"], [
            "src/reference.ts", "tests/test_reference.py", "tests/test_other_reference.py"])

    def test_nested_owner_cannot_leak_past_shallower_boundary(self):
        contract = self.extract(
            "### FILE BOUNDARIES\n#### Frontend\n##### Tester\n- tests/test_owned.py\n"
            "## NOTES\n### Backend\n- src/not_owned.ts\n")
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py"])

    def test_examples_do_not_open_or_add_to_ownership_sections(self):
        examples = (
            "> ## FILE BOUNDARIES\n> - tests/test_example.py\n",
            "    FILE BOUNDARIES:\n    - tests/test_example.py\n",
            "\tFILES TO MODIFY:\n\t- tests/test_example.py\n",
            "```md\nFILES TO MODIFY:\n- tests/test_example.py\n```\n",
            "~~~~markdown\n## FILE BOUNDARIES\n- tests/test_example.py\n~~~\n"
            "- tests/test_still_fenced.py\n~~~~\n",
        )
        for example in examples:
            for prefix in ("", "## FILE BOUNDARIES\n- tests/test_owned.py\n"):
                with self.subTest(example=example, prefix=prefix):
                    contract = self.extract(prefix + example + "## END\n")
                    self.assertEqual(contract["file_boundaries"],
                                     ["tests/test_owned.py"] if prefix else [])
                    self.assertEqual(contract["reference_files"], [])

    def test_fence_info_text_cannot_close_fence_and_indented_fence_cannot_open_it(self):
        contract = self.extract(
            "## FILE BOUNDARIES\n- tests/test_owned.py\n```md\n"
            "```not-a-closing-fence\n- tests/test_fenced.py\n```\n"
            "    ```\n- tests/test_second.py\n## END\n")
        self.assertEqual(contract["file_boundaries"], ["tests/test_owned.py", "tests/test_second.py"])

    def test_formatter_roundtrip_preserves_read_only_and_detects_conflicts(self):
        with patch("dotenv.load_dotenv", return_value=False):
            from orchestrator.contract_tools import format_contract_markdown
        original = self.extract(EXPLOIT_SPEC)
        formatted = format_contract_markdown(original)
        contract = self.extract(formatted)
        self.assertEqual(contract["file_boundaries"], original["file_boundaries"])
        self.assertEqual(contract["reference_files"], original["reference_files"])
        for spec in (formatted + "\n## FILE BOUNDARIES\n- tests/test_reference.py\n",
                     "## FILE BOUNDARIES\n- tests/test_reference.py\n" + formatted):
            with self.subTest(spec=spec), self.assertRaisesRegex(ValueError, "test_reference.py"):
                self.extract(spec)

    def test_dynamic_route_paths_use_actual_guarded_apply_and_do_not_authorize_truncated_aliases(self):
        path = "apps/web/test/(auth)/[[...userId]]/page.test.tsx"
        contract = self.extract(f"## FILE BOUNDARIES\n- `{path}`\n## NEEDS CONTEXT\n"
                                "- `apps/web/test/(auth)/[userId]/reference.test.tsx`\n")
        self.assertEqual(contract["file_boundaries"], [path])
        with self.scratch_pipeline() as (pipeline, root, _, events):
            result = pipeline.parse_and_apply_agent_file_operations(
                f"```write:{path}\nexport const fixture = true;\n```", "tester", contract=contract)
            self.assertEqual(result["created"], [path])
            self.assertTrue((root / path).is_file())
            for alias in ("apps/web/test/page.test.tsx", "/page.test.tsx",
                          "apps/web/test/(auth)/[userId]/reference.test.tsx"):
                with self.subTest(alias=alias), self.assertRaises(PermissionError):
                    pipeline._validate_tester_file_operations([("write", alias, "unsafe")], contract)

    def test_real_readiness_contract_all_test_paths_authorize_but_no_production_path_does(self):
        contract = self.extract(READINESS_PLANNER_SPEC)
        with self.scratch_pipeline() as (pipeline, _, _, _):
            for path in contract["file_boundaries"]:
                with self.subTest(path=path):
                    actions = [("write", path, "fixture")]
                    if path.startswith("apps/web/test/"):
                        pipeline._validate_tester_file_operations(actions, contract)
                    else:
                        with self.assertRaises(PermissionError):
                            pipeline._validate_tester_file_operations(actions, contract)

    def test_real_readiness_planner_output_keeps_all_owners_without_signature_leakage(self):
        # Real Planner output retained above, not a handbuilt contract dict.
        spec = READINESS_PLANNER_SPEC
        contract = self.extract(spec)
        # The boundary block is independent of later signatures/constraints/context.
        boundary_block = spec.split("## 2. FILE BOUNDARIES (exact paths)\n", 1)[1].split(
            "## 3. EXPORTED SIGNATURES", 1)[0]
        import re
        expected = []
        for path in re.findall(r"`([^`]+\.[A-Za-z0-9]+)`", boundary_block):
            if path not in expected:
                expected.append(path)
        self.assertEqual(contract["file_boundaries"], expected)
        self.assertEqual(contract["reference_files"], [])
        self.assertIn("apps/web/src/app/(auth)/login/page.tsx", expected)
        self.assertIn("apps/web/test/auth-accessibility.test.tsx", expected)
        self.assertIn("apps/web/package.json", expected)
        self.assertIn("pnpm-lock.yaml", expected)
        self.assertNotIn("src/theme/colors.ts", contract["file_boundaries"])
        self.assertTrue(any("status: AuthFormStatus;" in s for s in contract["exported_signatures"]))


if __name__ == "__main__":
    unittest.main()
