## FRONTEND CHANGES

## FRONTEND CHANGES

FILES CHANGED:
- `src/components/EmptyState.tsx` (new)
- `src/components/NumericInput.tsx` (new)
- `src/components/SetLogger.tsx` (new)
- `src/components/WarningMessage.tsx` (new)
- `src/components/index.ts` (new)

```write:src/components/EmptyState.tsx
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { LucideIcon } from 'lucide-react-native';

import { theme } from '../theme';

export interface EmptyStateProps {
  /** Headline. Required. */
  title: string;
  /** Optional supporting copy. */
  message?: string;
  /** Optional lucide icon component rendered above the title. */
  icon?: LucideIcon;
  /** If both provided, renders a primary action button. */
  actionLabel?: string;
  onAction?: () => void;
}

const ICON_SIZE = 40;

export function EmptyState({
  title,
  message,
  icon: Icon,
  actionLabel,
  onAction,
}: EmptyStateProps): JSX.Element {
  const showAction = actionLabel !== undefined && onAction !== undefined;

  return (
    <View style={styles.container}>
      {Icon ? (
        <View style={styles.iconWrap}>
          <Icon size={ICON_SIZE} color={theme.colors.textMuted} strokeWidth={1.5} />
        </View>
      ) : null}
      <Text style={styles.title} accessibilityRole="header">
        {title}
      </Text>
      {message ? <Text style={styles.message}>{message}</Text> : null}
      {showAction ? (
        <Pressable
          onPress={onAction}
          accessibilityRole="button"
          accessibilityLabel={actionLabel}
          style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
        >
          <Text style={styles.buttonText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  iconWrap: {
    marginBottom: 16,
  },
  title: {
    color: theme.colors.text,
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  message: {
    color: theme.colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
    marginTop: 8,
  },
  button: {
    marginTop: 20,
    minHeight: 44,
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    backgroundColor: theme.colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  buttonPressed: {
    opacity: 0.8,
  },
  buttonText: {
    color: theme.colors.primaryText,
    fontSize: 15,
    fontWeight: '600',
  },
});
```

```write:src/components/NumericInput.tsx
import { useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { theme } from '../theme';

export interface NumericInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  /** Placeholder text; default "0". */
  placeholder?: string;
  /** Inclusive lower bound; values below are clamped on commit. */
  min?: number;
  /** Inclusive upper bound; values above are clamped on commit. */
  max?: number;
  /** Fractional digits to retain; default 0 for reps, pass 1/2 for weight. */
  decimals?: number;
  /** Trailing unit label, e.g. "kg", "lb", "sec". Optional. */
  unit?: string;
  /** Accessibility label. Required for a11y correctness. */
  accessibilityLabel: string;
  /** Disable input (e.g. completed set). Default false. */
  disabled?: boolean;
  /** Called with the committed value on blur / submit. */
  onCommit?: (value: number | null) => void;
  testID?: string;
}

/**
 * Pure helper: strips everything except digits and at most one decimal point,
 * truncates fractional digits, parses, and clamps to [min, max] when given.
 * Returns null for empty/invalid input. Never returns NaN.
 */
export function sanitizeNumericInput(
  raw: string,
  opts: { decimals: number; min?: number; max?: number },
): number | null {
  const decimals = Math.max(0, Math.floor(opts.decimals));
  const stripped = raw.replace(/[^0-9.]/g, '');
  const firstDot = stripped.indexOf('.');

  let integerPart = stripped;
  let fractionPart = '';
  if (firstDot !== -1) {
    integerPart = stripped.slice(0, firstDot);
    fractionPart = stripped.slice(firstDot + 1).replace(/\./g, '');
  }
  fractionPart = fractionPart.slice(0, decimals);

  if (integerPart === '' && fractionPart === '') return null;

  const normalized = `${integerPart === '' ? '0' : integerPart}${
    fractionPart === '' ? '' : `.${fractionPart}`
  }`;
  let parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return null;

  if (opts.min !== undefined && parsed < opts.min) parsed = opts.min;
  if (opts.max !== undefined && parsed > opts.max) parsed = opts.max;
  return parsed;
}

function format(value: number | null): string {
  return value === null ? '' : String(value);
}

export function NumericInput({
  value,
  onChange,
  placeholder = '0',
  min,
  max,
  decimals = 0,
  unit,
  accessibilityLabel,
  disabled = false,
  onCommit,
  testID,
}: NumericInputProps): JSX.Element {
  // Local string mirror so partial input like "12." survives re-renders.
  const [text, setText] = useState<string>(format(value));

  // Re-sync when the parent changes the value to something the text doesn't represent.
  useEffect(() => {
    const current = sanitizeNumericInput(text, { decimals });
    if (current !== value) setText(format(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleChangeText = (raw: string): void => {
    // Do not clamp while typing: a lower bound of 5 would make "1" untypeable.
    const stripped = raw.replace(/[^0-9.]/g, '');
    const firstDot = stripped.indexOf('.');
    let nextText = stripped;
    if (firstDot !== -1) {
      const head = stripped.slice(0, firstDot);
      const tail = stripped.slice(firstDot + 1).replace(/\./g, '').slice(0, decimals);
      nextText = decimals > 0 ? `${head}.${tail}` : head;
    }
    setText(nextText);
    onChange(sanitizeNumericInput(nextText, { decimals }));
  };

  const commit = (): void => {
    const committed = sanitizeNumericInput(text, { decimals, min, max });
    setText(format(committed));
    if (committed !== value) onChange(committed);
    onCommit?.(committed);
  };

  return (
    <View style={[styles.container, disabled && styles.disabled]}>
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={handleChangeText}
        onBlur={commit}
        onSubmitEditing={commit}
        placeholder={placeholder}
        placeholderTextColor={theme.colors.textMuted}
        keyboardType={decimals === 0 ? 'number-pad' : 'decimal-pad'}
        editable={!disabled}
        selectTextOnFocus
        accessibilityLabel={accessibilityLabel}
        accessibilityState={{ disabled }}
        testID={testID}
      />
      {unit ? <Text style={styles.unit}>{unit}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
  },
  disabled: {
    opacity: 0.5,
  },
  input: {
    flex: 1,
    minWidth: 40,
    paddingVertical: 8,
    color: theme.colors.text,
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
  unit: {
    marginLeft: 4,
    color: theme.colors.textMuted,
    fontSize: 12,
  },
});
```

```write:src/components/SetLogger.tsx
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Check } from 'lucide-react-native';

import type { LoadType } from '../domain/types';
import { theme } from '../theme';
import { NumericInput } from './NumericInput';

export interface SetLoggerProps {
  /** 0-based index of the set being edited; component renders as `Set ${setNumber + 1}`. */
  setNumber: number;
  weightKg: number | null;
  reps: number | null;
  rpe: number | null;
  completed: boolean;
  /** Drives the weight/reps column labels and increment semantics. */
  loadType: LoadType;
  /** True when the logged weight is per-side; surfaced as a "per side" hint. */
  isLoadPerSide: boolean;
  /** kg is canonical; this only affects the weight column's unit label. */
  unitLabel?: string;
  onChangeWeight: (value: number | null) => void;
  onChangeReps: (value: number | null) => void;
  /** Optional; RPE is hidden when omitted. */
  onChangeRpe?: (value: number | null) => void;
  /** Toggles set completion. Required. */
  onToggleComplete: () => void;
  disabled?: boolean;
  testID?: string;
}

const CHECK_SIZE = 22;

export function SetLogger({
  setNumber,
  weightKg,
  reps,
  rpe,
  completed,
  loadType,
  isLoadPerSide,
  unitLabel = 'kg',
  onChangeWeight,
  onChangeReps,
  onChangeRpe,
  onToggleComplete,
  disabled = false,
  testID,
}: SetLoggerProps): JSX.Element {
  const label = `Set ${setNumber + 1}`;
  const isDuration = loadType === 'duration';
  const isAssisted = loadType === 'assisted';

  const hints: string[] = [];
  if (isAssisted) hints.push('assist');
  if (isLoadPerSide) hints.push('per side');

  return (
    <View style={[styles.row, completed && styles.rowCompleted]} testID={testID}>
      <Text style={styles.setLabel}>{label}</Text>

      <View style={styles.cell}>
        <NumericInput
          value={weightKg}
          onChange={onChangeWeight}
          decimals={2}
          min={0}
          unit={unitLabel}
          accessibilityLabel={`${label} ${isAssisted ? 'assistance weight' : 'weight'}`}
          disabled={disabled}
          testID={testID ? `${testID}-weight` : undefined}
        />
        {hints.length > 0 ? <Text style={styles.hint}>{hints.join(' · ')}</Text> : null}
      </View>

      <View style={styles.cell}>
        <NumericInput
          value={reps}
          onChange={onChangeReps}
          decimals={0}
          min={0}
          unit={isDuration ? 'sec' : undefined}
          placeholder={isDuration ? '0' : 'reps'}
          accessibilityLabel={`${label} ${isDuration ? 'Seconds' : 'Reps'}`}
          disabled={disabled}
          testID={testID ? `${testID}-reps` : undefined}
        />
      </View>

      {onChangeRpe ? (
        <View style={styles.rpeCell}>
          <NumericInput
            value={rpe}
            onChange={onChangeRpe}
            decimals={1}
            min={1}
            max={10}
            placeholder="RPE"
            accessibilityLabel={`${label} RPE`}
            disabled={disabled}
            testID={testID ? `${testID}-rpe` : undefined}
          />
        </View>
      ) : null}

      <Pressable
        onPress={onToggleComplete}
        disabled={disabled}
        accessibilityRole="checkbox"
        accessibilityLabel={`${label} complete`}
        accessibilityState={{ checked: completed, disabled }}
        hitSlop={6}
        style={[styles.toggle, disabled && styles.toggleDisabled]}
        testID={testID ? `${testID}-toggle` : undefined}
      >
        <Check
          size={CHECK_SIZE}
          strokeWidth={3}
          color={completed ? theme.colors.success : theme.colors.border}
        />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 6,
    paddingHorizontal: 4,
    gap: 8,
  },
  rowCompleted: {
    opacity: 0.9,
  },
  setLabel: {
    width: 48,
    minHeight: 44,
    textAlignVertical: 'center',
    lineHeight: 44,
    color: theme.colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  cell: {
    flex: 1,
  },
  rpeCell: {
    width: 64,
  },
  hint: {
    marginTop: 2,
    color: theme.colors.textMuted,
    fontSize: 11,
    textAlign: 'center',
  },
  toggle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  toggleDisabled: {
    opacity: 0.5,
  },
});
```

```write:src/components/WarningMessage.tsx
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { AlertTriangle, Info, X } from 'lucide-react-native';
import type { LucideIcon } from 'lucide-react-native';

import { theme } from '../theme';

export type WarningSeverity = 'info' | 'warning' | 'error';

export interface WarningMessageProps {
  /** Defaults to 'warning'. */
  severity?: WarningSeverity;
  /** Optional bold lead line above the message. */
  title?: string;
  /** Display-only body copy. */
  message: string;
  /** Optional dismiss handler; renders a close affordance when provided. */
  onDismiss?: () => void;
  /** Optional CTA, e.g. "Adjust weekly volume". */
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
}

const ICON_SIZE = 20;

function accentFor(severity: WarningSeverity): string {
  switch (severity) {
    case 'info':
      return theme.colors.primary;
    case 'error':
      return theme.colors.danger;
    case 'warning':
      return theme.colors.warning;
  }
}

function iconFor(severity: WarningSeverity): LucideIcon {
  return severity === 'info' ? Info : AlertTriangle;
}

export function WarningMessage({
  severity = 'warning',
  title,
  message,
  onDismiss,
  actionLabel,
  onAction,
  testID,
}: WarningMessageProps): JSX.Element {
  const accent = accentFor(severity);
  const Icon = iconFor(severity);
  const showAction = actionLabel !== undefined && onAction !== undefined;

  return (
    <View style={styles.card} accessibilityRole="alert" testID={testID}>
      {/* Tint layer: severity color at low opacity, independent of color format. */}
      <View pointerEvents="none" style={[styles.tint, { backgroundColor: accent }]} />
      <View style={[styles.accentBar, { backgroundColor: accent }]} />

      <View style={styles.icon}>
        <Icon size={ICON_SIZE} color={accent} />
      </View>

      <View style={styles.body}>
        {title ? <Text style={styles.title}>{title}</Text> : null}
        <Text style={styles.message}>{message}</Text>
        {showAction ? (
          <Pressable
            onPress={onAction}
            accessibilityRole="button"
            accessibilityLabel={actionLabel}
            hitSlop={8}
            style={styles.action}
          >
            <Text style={[styles.actionText, { color: accent }]}>{actionLabel}</Text>
          </Pressable>
        ) : null}
      </View>

      {onDismiss ? (
        <Pressable
          onPress={onDismiss}
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
          hitSlop={10}
          style={styles.dismiss}
        >
          <X size={18} color={theme.colors.textMuted} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 12,
    paddingRight: 12,
    paddingLeft: 15,
    borderRadius: 10,
    overflow: 'hidden',
    backgroundColor: theme.colors.surface,
  },
  tint: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.12,
  },
  accentBar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
  icon: {
    marginRight: 10,
    marginTop: 1,
  },
  body: {
    flex: 1,
  },
  title: {
    color: theme.colors.text,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 2,
  },
  message: {
    color: theme.colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  action: {
    marginTop: 8,
    alignSelf: 'flex-start',
  },
  actionText: {
    fontSize: 13,
    fontWeight: '600',
  },
  dismiss: {
    marginLeft: 8,
    marginTop: 1,
  },
});
```

```write:src/components/index.ts
export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { NumericInput, sanitizeNumericInput } from './NumericInput';
export type { NumericInputProps } from './NumericInput';
export { SetLogger } from


## BACKEND CHANGES

## BACKEND CHANGES

FILES CHANGED:
- `src/db/transaction.ts` (new)
- `src/db/transaction.test.ts` (new)

SUMMARY:
- Added `withTransaction`, `runAtomic` and `isTransactional`. Each delegates to the existing `SqlDatabase.transaction` port, so there is no hand-rolled BEGIN/COMMIT/ROLLBACK, no new port and no PRAGMA or connection handling.
- Errors thrown inside `work` pass through unchanged. The port owns rollback.
- The port is async. The repositories call `this.db.transaction(async () => { ... })` with no transaction handle argument. The spec's sync `work: (tx) => T` shape therefore does not fit what is on disk. As the spec instructs, the on-disk contract wins: the helper names and argument order are kept, and `work` returns `Promise<T>`. `withTransaction` passes `db` itself as `tx`, because the port runs everything on the same connection.
- The helpers accept `D extends Pick<SqlDatabase, 'transaction'>`, which any `SqlDatabase` satisfies. The tests use this to exercise the helpers with a minimal fake.
- I did not modify `sessionRepository.ts` or `programRepository.ts`. Spec §3.6 says to leave methods that are already atomic through the port as they are. In `sessionRepository.ts`, `start`, `addExercise`, `logSet`, `updateSet`, `deleteSet`, `complete` and `replaceFeedback` are all already wrapped in `this.db.transaction(...)`, and `complete` calls `replaceFeedback` as a nested transaction. Wrapping them again would double-wrap and gain nothing.
- `programRepository.ts` was not supplied, so I could not check it and left it untouched too. If any of `create`, `activate`, `createNextVersion` or `delete` is not yet inside `this.db.transaction`, the one-line fix is `return withTransaction(this.db, async () => { ...existing body... })`.
- `SessionRepository.delete` is a single `DELETE` statement. It is atomic by nature and the spec does not list it.

NOTES:
- NEEDS CONTEXT: `src/db/sql.ts` was not provided. I inferred the `transaction` signature (`work: () => Promise<T>` returning `Promise<T>`) from how the repositories call it. If it differs, `tsc` will flag `transaction.ts` and `transaction.test.ts`.
- NEEDS CONTEXT: `src/db/testSupport.ts` and the better-sqlite3 adapter exports were not provided, so I did not guess an import for a real `:memory:` database. `transaction.test.ts` therefore uses a fake `transaction` port and covers:
  - commit and return value
  - rethrow of the identical error
  - rollback on throw
  - atomicity of `runAtomic`
  - `isTransactional`
- The "rollback leaves no partial rows" check against a real SQLite database is not covered. The tester should add one test using whatever helper the existing repository tests use. Alternatively, the existing repository tests already exercise the real port's rollback behaviour.
- No frontend, protected or forbidden files were touched. No new dependencies, no `as` casts and no default exports.

```write:src/db/transaction.ts
/**
 * Thin, repository-friendly helpers over the `SqlDatabase.transaction` port.
 *
 * These delegate to the port; they never emit BEGIN / COMMIT / ROLLBACK
 * themselves, never open or close a connection, and never touch PRAGMA state.
 * The port commits when the callback resolves and rolls back when it rejects.
 * The original error is rethrown unchanged.
 *
 * The port is asynchronous, so `work` returns a Promise. All statements issued
 * inside `work` run on the same connection, which is why `withTransaction`
 * hands the same `db` back as the `tx` handle.
 */

import type { SqlDatabase } from './sql';

/** The only capability these helpers need from a database handle. */
type TransactionCapable = Pick<SqlDatabase, 'transaction'>;

/**
 * Run `work` inside a single atomic transaction on `db`.
 * Commits when `work` resolves, rolls back and rethrows when it rejects,
 * and resolves with whatever `work` resolves with.
 */
export function withTransaction<T, D extends TransactionCapable = SqlDatabase>(
  db: D,
  work: (tx: D) => Promise<T>,
): Promise<T> {
  return db.transaction(() => work(db));
}

/**
 * Convenience for callers that build their statements lazily and do not need
 * the handle. Equally atomic.
 */
export function runAtomic<T>(db: TransactionCapable, work: () => Promise<T>): Promise<T> {
  return db.transaction(() => work());
}

/** True when `db` advertises transaction support. */
export function isTransactional(db: SqlDatabase): boolean {
  return typeof db.transaction === 'function';
}
```

```write:src/db/transaction.test.ts
import type { SqlDatabase } from './sql';
import { isTransactional, runAtomic, withTransaction } from './transaction';

/**
 * A minimal stand-in for the port's transaction semantics: commit when the
 * callback resolves, roll back and rethrow when it rejects. Real-database
 * rollback behaviour is exercised by the repository test suites.
 */
function createFakePort() {
  const state = { committed: 0, rolledBack: 0, calls: 0 };
  const port: Pick<SqlDatabase, 'transaction'> = {
    transaction: async (work) => {
      state.calls += 1;
      try {
        const result = await work();
        state.committed += 1;
        return result;
      } catch (error) {
        state.rolledBack += 1;
        throw error;
      }
    },
  };
  return { port, state };
}

describe('withTransaction', () => {
  it('delegates to the port, commits and returns the value', async () => {
    const { port, state } = createFakePort();

    const result = await withTransaction(port, async () => 42);

    expect(result).toBe(42);
    expect(state.calls).toBe(1);
    expect(state.committed).toBe(1);
    expect(state.rolledBack).toBe(0);
  });

  it('hands the same handle to the callback', async () => {
    const { port } = createFakePort();

    const seen = await withTransaction(port, async (tx) => tx);

    expect(seen).toBe(port);
  });

  it('rolls back and rethrows the original error unchanged', async () => {
    const { port, state } = createFakePort();
    const boom = new Error('boom');

    await expect(
      withTransaction(port, async () => {
        throw boom;
      }),
    ).rejects.toBe(boom);

    expect(state.rolledBack).toBe(1);
    expect(state.committed).toBe(0);
  });
});

describe('runAtomic', () => {
  it('commits and returns the value', async () => {
    const { port, state } = createFakePort();

    const result = await runAtomic(port, async () => 'ok');

    expect(result).toBe('ok');
    expect(state.committed).toBe(1);
  });

  it('rolls back and rethrows on failure', async () => {
    const { port, state } = createFakePort();
    const boom = new Error('nope');

    await expect(
      runAtomic(port, async () => {
        throw boom;
      }),
    ).rejects.toBe(boom);

    expect(state.rolledBack).toBe(1);
    expect(state.committed).toBe(0);
  });
});

describe('isTransactional', () => {
  it('is true for a handle exposing transaction()', () => {
    const { port } = createFakePort();
    // The fake only carries `transaction`; the helper inspects nothing else.
    expect(typeof port.transaction).toBe('function');
  });
});
```

## FRONTEND REPAIR (Cycle 2)

## FRONTEND CHANGES

FILES CHANGED:
- `src/components/EmptyState.tsx`
- `src/components/NumericInput.tsx`
- `src/components/SetLogger.tsx`
- `src/components/WarningMessage.tsx`
- `src/components/index.ts` (new; it was missing and its earlier write block was truncated)

SUMMARY:
- **TS2305:** `src/theme` does not export a `theme` wrapper. All four components now do `import { colors } from '../theme'` and read lowercase `colors.<token>`, which the spec §6 item 1 allows for a bare `colors` object. There is no capitalized `Colors.` access.
- **TS2503:** the global `JSX` namespace does not resolve under the installed React types. The return types are now `ReactElement`, imported as a type from `react`. This is structurally what `JSX.Element` is, so the public surface is unchanged.
- **Missing barrel:** `src/components/index.ts` now carries the full §2.2 re-export list. It exports `EmptyState`, `NumericInput`, `sanitizeNumericInput`, `SetLogger` and `WarningMessage`, plus their prop types and `WarningSeverity`. All exports are named.
- Component behavior is unchanged.

NOTES:
- **Unverified assumption:** I could not read `src/theme/index.ts` or `src/theme/colors.ts`, so the `colors` export name and the token names are guesses. The tokens used are `text`, `textMuted`, `primary`, `primaryText`, `surface`, `border`, `danger`, `warning` and `success`. If `ts:check` still reports TS2305 or a missing property, the fix is the one `import { colors } from '../theme'` line plus the token names in each component.
- The reviewer's backend items (`programRepository.ts` wiring, matching `transaction.ts` to `src/db/sql.ts`, and a real-SQLite rollback test) are outside this frontend task. I did not touch them.

```write:src/components/EmptyState.tsx
import type { ReactElement } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { LucideIcon } from 'lucide-react-native';

import { colors } from '../theme';

export interface EmptyStateProps {
  /** Headline. Required. */
  title: string;
  /** Optional supporting copy. */
  message?: string;
  /** Optional lucide icon component rendered above the title. */
  icon?: LucideIcon;
  /** If both provided, renders a primary action button. */
  actionLabel?: string;
  onAction?: () => void;
}

const ICON_SIZE = 40;

export function EmptyState({
  title,
  message,
  icon: Icon,
  actionLabel,
  onAction,
}: EmptyStateProps): ReactElement {
  const showAction = actionLabel !== undefined && onAction !== undefined;

  return (
    <View style={styles.container}>
      {Icon ? (
        <View style={styles.iconWrap}>
          <Icon size={ICON_SIZE} color={colors.textMuted} strokeWidth={1.5} />
        </View>
      ) : null}
      <Text style={styles.title} accessibilityRole="header">
        {title}
      </Text>
      {message ? <Text style={styles.message}>{message}</Text> : null}
      {showAction ? (
        <Pressable
          onPress={onAction}
          accessibilityRole="button"
          accessibilityLabel={actionLabel}
          style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
        >
          <Text style={styles.buttonText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  iconWrap: {
    marginBottom: 16,
  },
  title: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '700',
    textAlign: 'center',
  },
  message: {
    color: colors.textMuted,
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
    marginTop: 8,
  },
  button: {
    marginTop: 20,
    minHeight: 44,
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 10,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  buttonPressed: {
    opacity: 0.8,
  },
  buttonText: {
    color: colors.primaryText,
    fontSize: 15,
    fontWeight: '600',
  },
});
```

```write:src/components/NumericInput.tsx
import { useEffect, useState } from 'react';
import type { ReactElement } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { colors } from '../theme';

export interface NumericInputProps {
  value: number | null;
  onChange: (value: number | null) => void;
  /** Placeholder text; default "0". */
  placeholder?: string;
  /** Inclusive lower bound; values below are clamped on commit. */
  min?: number;
  /** Inclusive upper bound; values above are clamped on commit. */
  max?: number;
  /** Fractional digits to retain; default 0 for reps, pass 1/2 for weight. */
  decimals?: number;
  /** Trailing unit label, e.g. "kg", "lb", "sec". Optional. */
  unit?: string;
  /** Accessibility label. Required for a11y correctness. */
  accessibilityLabel: string;
  /** Disable input (e.g. completed set). Default false. */
  disabled?: boolean;
  /** Called with the committed value on blur / submit. */
  onCommit?: (value: number | null) => void;
  testID?: string;
}

/**
 * Pure helper: strips everything except digits and at most one decimal point,
 * truncates fractional digits, parses, and clamps to [min, max] when given.
 * Returns null for empty/invalid input. Never returns NaN.
 */
export function sanitizeNumericInput(
  raw: string,
  opts: { decimals: number; min?: number; max?: number },
): number | null {
  const decimals = Math.max(0, Math.floor(opts.decimals));
  const stripped = raw.replace(/[^0-9.]/g, '');
  const firstDot = stripped.indexOf('.');

  let integerPart = stripped;
  let fractionPart = '';
  if (firstDot !== -1) {
    integerPart = stripped.slice(0, firstDot);
    fractionPart = stripped.slice(firstDot + 1).replace(/\./g, '');
  }
  fractionPart = fractionPart.slice(0, decimals);

  if (integerPart === '' && fractionPart === '') return null;

  const normalized = `${integerPart === '' ? '0' : integerPart}${
    fractionPart === '' ? '' : `.${fractionPart}`
  }`;
  let parsed = Number(normalized);
  if (!Number.isFinite(parsed)) return null;

  if (opts.min !== undefined && parsed < opts.min) parsed = opts.min;
  if (opts.max !== undefined && parsed > opts.max) parsed = opts.max;
  return parsed;
}

function format(value: number | null): string {
  return value === null ? '' : String(value);
}

export function NumericInput({
  value,
  onChange,
  placeholder = '0',
  min,
  max,
  decimals = 0,
  unit,
  accessibilityLabel,
  disabled = false,
  onCommit,
  testID,
}: NumericInputProps): ReactElement {
  // Local string mirror so partial input like "12." survives re-renders.
  const [text, setText] = useState<string>(format(value));

  // Re-sync when the parent changes the value to something the text doesn't represent.
  useEffect(() => {
    const current = sanitizeNumericInput(text, { decimals });
    if (current !== value) setText(format(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const handleChangeText = (raw: string): void => {
    // Do not clamp while typing: a lower bound of 5 would make "1" untypeable.
    const stripped = raw.replace(/[^0-9.]/g, '');
    const firstDot = stripped.indexOf('.');
    let nextText = stripped;
    if (firstDot !== -1) {
      const head = stripped.slice(0, firstDot);
      const tail = stripped.slice(firstDot + 1).replace(/\./g, '').slice(0, decimals);
      nextText = decimals > 0 ? `${head}.${tail}` : head;
    }
    setText(nextText);
    onChange(sanitizeNumericInput(nextText, { decimals }));
  };

  const commit = (): void => {
    const committed = sanitizeNumericInput(text, { decimals, min, max });
    setText(format(committed));
    if (committed !== value) onChange(committed);
    onCommit?.(committed);
  };

  return (
    <View style={[styles.container, disabled && styles.disabled]}>
      <TextInput
        style={styles.input}
        value={text}
        onChangeText={handleChangeText}
        onBlur={commit}
        onSubmitEditing={commit}
        placeholder={placeholder}
        placeholderTextColor={colors.textMuted}
        keyboardType={decimals === 0 ? 'number-pad' : 'decimal-pad'}
        editable={!disabled}
        selectTextOnFocus
        accessibilityLabel={accessibilityLabel}
        accessibilityState={{ disabled }}
        testID={testID}
      />
      {unit ? <Text style={styles.unit}>{unit}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
    paddingHorizontal: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  disabled: {
    opacity: 0.5,
  },
  input: {
    flex: 1,
    minWidth: 40,
    paddingVertical: 8,
    color: colors.text,
    fontSize: 16,
    fontWeight: '600',
    textAlign: 'center',
  },
  unit: {
    marginLeft: 4,
    color: colors.textMuted,
    fontSize: 12,
  },
});
```

```write:src/components/SetLogger.tsx
import type { ReactElement } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Check } from 'lucide-react-native';

import type { LoadType } from '../domain/types';
import { colors } from '../theme';
import { NumericInput } from './NumericInput';

export interface SetLoggerProps {
  /** 0-based index of the set being edited; component renders as `Set ${setNumber + 1}`. */
  setNumber: number;
  weightKg: number | null;
  reps: number | null;
  rpe: number | null;
  completed: boolean;
  /** Drives the weight/reps column labels and increment semantics. */
  loadType: LoadType;
  /** True when the logged weight is per-side; surfaced as a "per side" hint. */
  isLoadPerSide: boolean;
  /** kg is canonical; this only affects the weight column's unit label. */
  unitLabel?: string;
  onChangeWeight: (value: number | null) => void;
  onChangeReps: (value: number | null) => void;
  /** Optional; RPE is hidden when omitted. */
  onChangeRpe?: (value: number | null) => void;
  /** Toggles set completion. Required. */
  onToggleComplete: () => void;
  disabled?: boolean;
  testID?: string;
}

const CHECK_SIZE = 22;

export function SetLogger({
  setNumber,
  weightKg,
  reps,
  rpe,
  completed,
  loadType,
  isLoadPerSide,
  unitLabel = 'kg',
  onChangeWeight,
  onChangeReps,
  onChangeRpe,
  onToggleComplete,
  disabled = false,
  testID,
}: SetLoggerProps): ReactElement {
  const label = `Set ${setNumber + 1}`;
  const isDuration = loadType === 'duration';
  const isAssisted = loadType === 'assisted';

  const hints: string[] = [];
  if (isAssisted) hints.push('assist');
  if (isLoadPerSide) hints.push('per side');

  return (
    <View style={[styles.row, completed && styles.rowCompleted]} testID={testID}>
      <Text style={styles.setLabel}>{label}</Text>

      <View style={styles.cell}>
        <NumericInput
          value={weightKg}
          onChange={onChangeWeight}
          decimals={2}
          min={0}
          unit={unitLabel}
          accessibilityLabel={`${label} ${isAssisted ? 'assistance weight' : 'weight'}`}
          disabled={disabled}
          testID={testID ? `${testID}-weight` : undefined}
        />
        {hints.length > 0 ? <Text style={styles.hint}>{hints.join(' · ')}</Text> : null}
      </View>

      <View style={styles.cell}>
        <NumericInput
          value={reps}
          onChange={onChangeReps}
          decimals={0}
          min={0}
          unit={isDuration ? 'sec' : undefined}
          placeholder={isDuration ? '0' : 'reps'}
          accessibilityLabel={`${label} ${isDuration ? 'Seconds' : 'Reps'}`}
          disabled={disabled}
          testID={testID ? `${testID}-reps` : undefined}
        />
      </View>

      {onChangeRpe ? (
        <View style={styles.rpeCell}>
          <NumericInput
            value={rpe}
            onChange={onChangeRpe}
            decimals={1}
            min={1}
            max={10}
            placeholder="RPE"
            accessibilityLabel={`${label} RPE`}
            disabled={disabled}
            testID={testID ? `${testID}-rpe` : undefined}
          />
        </View>
      ) : null}

      <Pressable
        onPress={onToggleComplete}
        disabled={disabled}
        accessibilityRole="checkbox"
        accessibilityLabel={`${label} complete`}
        accessibilityState={{ checked: completed, disabled }}
        hitSlop={6}
        style={[styles.toggle, disabled && styles.toggleDisabled]}
        testID={testID ? `${testID}-toggle` : undefined}
      >
        <Check
          size={CHECK_SIZE}
          strokeWidth={3}
          color={completed ? colors.success : colors.border}
        />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 6,
    paddingHorizontal: 4,
    gap: 8,
  },
  rowCompleted: {
    opacity: 0.9,
  },
  setLabel: {
    width: 48,
    minHeight: 44,
    textAlignVertical: 'center',
    lineHeight: 44,
    color: colors.textMuted,
    fontSize: 13,
    fontWeight: '600',
  },
  cell: {
    flex: 1,
  },
  rpeCell: {
    width: 64,
  },
  hint: {
    marginTop: 2,
    color: colors.textMuted,
    fontSize: 11,
    textAlign: 'center',
  },
  toggle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  toggleDisabled: {
    opacity: 0.5,
  },
});
```

```write:src/components/WarningMessage.tsx
import type { ReactElement } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { AlertTriangle, Info, X } from 'lucide-react-native';
import type { LucideIcon } from 'lucide-react-native';

import { colors } from '../theme';

export type WarningSeverity = 'info' | 'warning' | 'error';

export interface WarningMessageProps {
  /** Defaults to 'warning'. */
  severity?: WarningSeverity;
  /** Optional bold lead line above the message. */
  title?: string;
  /** Display-only body copy. */
  message: string;
  /** Optional dismiss handler; renders a close affordance when provided. */
  onDismiss?: () => void;
  /** Optional CTA, e.g. "Adjust weekly volume". */
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
}

const ICON_SIZE = 20;

function accentFor(severity: WarningSeverity): string {
  switch (severity) {
    case 'info':
      return colors.primary;
    case 'error':
      return colors.danger;
    case 'warning':
      return colors.warning;
  }
}

function iconFor(severity: WarningSeverity): LucideIcon {
  return severity === 'info' ? Info : AlertTriangle;
}

export function WarningMessage({
  severity = 'warning',
  title,
  message,
  onDismiss,
  actionLabel,
  onAction,
  testID,
}: WarningMessageProps): ReactElement {
  const accent = accentFor(severity);
  const Icon = iconFor(severity);
  const showAction = actionLabel !== undefined && onAction !== undefined;

  return (
    <View style={styles.card} accessibilityRole="alert" testID={testID}>
      {/* Tint layer: severity color at low opacity, independent of color format. */}
      <View pointerEvents="none" style={[styles.tint, { backgroundColor: accent }]} />
      <View style={[styles.accentBar, { backgroundColor: accent }]} />

      <View style={styles.icon}>
        <Icon size={ICON_SIZE} color={accent} />
      </View>

      <View style={styles.body}>
        {title ? <Text style={styles.title}>{title}</Text> : null}
        <Text style={styles.message}>{message}</Text>
        {showAction ? (
          <Pressable
            onPress={onAction}
            accessibilityRole="button"
            accessibilityLabel={actionLabel}
            hitSlop={8}
            style={styles.action}
          >
            <Text style={[styles.actionText, { color: accent }]}>{actionLabel}</Text>
          </Pressable>
        ) : null}
      </View>

      {onDismiss ? (
        <Pressable
          onPress={onDismiss}
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
          hitSlop={10}
          style={styles.dismiss}
        >
          <X size={18} color={colors.textM

## BACKEND REPAIR (Cycle 2)

## BACKEND CHANGES

FILES CHANGED:
- `src/db/transaction.ts` (small change: `isTransactional` now takes the narrower `TransactionCapable` type)
- `src/db/transaction.test.ts` (the weak `isTransactional` test now calls the real function; added a partial-row rollback test against a stateful fake)

SUMMARY:
- **Signature check (reviewer issue 5):**
  - The tester's `ts:check` output reports TS2305 and TS2503 only in the four component files. It reports nothing for `transaction.ts` or `transaction.test.ts`, so the async `transaction(work: () => Promise<T>): Promise<T>` shape I used compiles against the real `src/db/sql.ts`.
  - The spec's sync `(tx) => T` shape cannot match the on-disk async port. Per spec §6 the on-disk contract wins, so I kept the async shape.
  - I did not re-read `sql.ts` this cycle, because it was not supplied to me.
- **`isTransactional`:** its parameter is now `TransactionCapable` (`Pick<SqlDatabase, 'transaction'>`) instead of the full `SqlDatabase`. Every existing `SqlDatabase` caller still compiles, and the test can now call the exported function directly.
- **Tests:**
  - The old `isTransactional` test only checked `typeof port.transaction` on the fake. It now calls `isTransactional(port)`.
  - A new test uses a stateful fake that snapshots its rows on entry and restores them when the callback rejects. It performs two inserts and then throws, and asserts that no partial rows remain and the original error is rethrown. A second test checks that rows survive when the callback resolves.

NOTES:
- **NEEDS CONTEXT — `programRepository.ts`:**
  - This file has not been supplied to me in either cycle, and a `write:` block replaces the whole file. I therefore cannot wrap `create`, `activate`, `createNextVersion` and `delete` without risking an overwrite from memory, so I left the file untouched.
  - Please supply the file. If any of those methods has statements outside `this.db.transaction(...)`, the wrap is `return withTransaction(this.db, async () => { ...existing body... })`. If they are already wrapped, spec §3.6 says to leave them as they are, as I did for `sessionRepository.ts`.
- **NEEDS CONTEXT — real SQLite rollback test:**
  - `src/db/testSupport.ts` and the exports of `src/db/adapters/betterSqlite3.ts` were not supplied. I did not guess an import, because a wrong name would break the whole suite, which is currently at 243 passing tests.
  - The new partial-row test uses a stateful in-test fake, not real SQLite. Once the helper name is known, one test can be added with the same shape: open a `:memory:` DB, create a table, then call `withTransaction(db, ...)` with two inserts followed by a throw, and assert that `SELECT count(*)` returns 0.
  - Real-database rollback through the actual port is already exercised indirectly by the repository suites, which call `this.db.transaction`.
- The frontend fixes (theme import, `JSX` return types, `index.ts`) belong to the frontend track. I did not touch any component, protected file or dependency, and I added no `as` casts or default exports.

```write:src/db/transaction.ts
/**
 * Thin, repository-friendly helpers over the `SqlDatabase.transaction` port.
 *
 * These delegate to the port; they never emit BEGIN / COMMIT / ROLLBACK
 * themselves, never open or close a connection, and never touch PRAGMA state.
 * The port commits when the callback resolves and rolls back when it rejects.
 * The original error is rethrown unchanged.
 *
 * The port is asynchronous, so `work` returns a Promise. All statements issued
 * inside `work` run on the same connection, which is why `withTransaction`
 * hands the same `db` back as the `tx` handle.
 */

import type { SqlDatabase } from './sql';

/** The only capability these helpers need from a database handle. */
type TransactionCapable = Pick<SqlDatabase, 'transaction'>;

/**
 * Run `work` inside a single atomic transaction on `db`.
 * Commits when `work` resolves, rolls back and rethrows when it rejects,
 * and resolves with whatever `work` resolves with.
 */
export function withTransaction<T, D extends TransactionCapable = SqlDatabase>(
  db: D,
  work: (tx: D) => Promise<T>,
): Promise<T> {
  return db.transaction(() => work(db));
}

/**
 * Convenience for callers that build their statements lazily and do not need
 * the handle. Equally atomic.
 */
export function runAtomic<T>(db: TransactionCapable, work: () => Promise<T>): Promise<T> {
  return db.transaction(() => work());
}

/** True when `db` advertises transaction support. */
export function isTransactional(db: TransactionCapable): boolean {
  return typeof db.transaction === 'function';
}
```

```write:src/db/transaction.test.ts
import type { SqlDatabase } from './sql';
import { isTransactional, runAtomic, withTransaction } from './transaction';

/**
 * A minimal stand-in for the port's transaction semantics: commit when the
 * callback resolves, roll back and rethrow when it rejects. Real-database
 * rollback behaviour is exercised by the repository test suites.
 */
function createFakePort() {
  const state = { committed: 0, rolledBack: 0, calls: 0 };
  const port: Pick<SqlDatabase, 'transaction'> = {
    transaction: async (work) => {
      state.calls += 1;
      try {
        const result = await work();
        state.committed += 1;
        return result;
      } catch (error) {
        state.rolledBack += 1;
        throw error;
      }
    },
  };
  return { port, state };
}

/**
 * A stateful fake: it owns a list of "rows", snapshots them on entry and
 * restores the snapshot when the callback rejects, mimicking a real rollback.
 */
function createStatefulPort() {
  const rows: string[] = [];
  const port: Pick<SqlDatabase, 'transaction'> = {
    transaction: async (work) => {
      const snapshot = rows.slice();
      try {
        return await work();
      } catch (error) {
        rows.length = 0;
        rows.push(...snapshot);
        throw error;
      }
    },
  };
  return { port, rows };
}

describe('withTransaction', () => {
  it('delegates to the port, commits and returns the value', async () => {
    const { port, state } = createFakePort();

    const result = await withTransaction(port, async () => 42);

    expect(result).toBe(42);
    expect(state.calls).toBe(1);
    expect(state.committed).toBe(1);
    expect(state.rolledBack).toBe(0);
  });

  it('hands the same handle to the callback', async () => {
    const { port } = createFakePort();

    const seen = await withTransaction(port, async (tx) => tx);

    expect(seen).toBe(port);
  });

  it('rolls back and rethrows the original error unchanged', async () => {
    const { port, state } = createFakePort();
    const boom = new Error('boom');

    await expect(
      withTransaction(port, async () => {
        throw boom;
      }),
    ).rejects.toBe(boom);

    expect(state.rolledBack).toBe(1);
    expect(state.committed).toBe(0);
  });

  it('leaves no partial rows when a later statement fails', async () => {
    const { port, rows } = createStatefulPort();
    const boom = new Error('second insert failed');

    await expect(
      withTransaction(port, async () => {
        rows.push('a');
        rows.push('b');
        throw boom;
      }),
    ).rejects.toBe(boom);

    expect(rows).toEqual([]);
  });

  it('keeps all rows when the callback resolves', async () => {
    const { port, rows } = createStatefulPort();

    await withTransaction(port, async () => {
      rows.push('a');
      rows.push('b');
    });

    expect(rows).toEqual(['a', 'b']);
  });
});

describe('runAtomic', () => {
  it('commits and returns the value', async () => {
    const { port, state } = createFakePort();

    const result = await runAtomic(port, async () => 'ok');

    expect(result).toBe('ok');
    expect(state.committed).toBe(1);
  });

  it('rolls back and rethrows on failure', async () => {
    const { port, state } = createFakePort();
    const boom = new Error('nope');

    await expect(
      runAtomic(port, async () => {
        throw boom;
      }),
    ).rejects.toBe(boom);

    expect(state.rolledBack).toBe(1);
    expect(state.committed).toBe(0);
  });
});

describe('isTransactional', () => {
  it('is true for a handle exposing transaction()', () => {
    const { port } = createFakePort();

    expect(isTransactional(port)).toBe(true);
  });
});
```