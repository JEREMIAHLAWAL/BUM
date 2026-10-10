# Feature 4: Progress & PR Analytics Screen (`src/app/(app)/analytics.tsx`)

## 1. Target Isolation & File Boundaries (STRICT)
- Create/modify ONLY these 2 exact files:
  1. `src/app/(app)/analytics.tsx` (SINGLE, self-contained screen file — DO NOT create any files under `src/components/Analytics/` or anywhere else).
  2. `src/app/(app)/_layout.tsx` (Register the Analytics tab).
- Do NOT touch `package.json`, `src/theme/`, `src/domain/`, or any other screen files.

## 2. Exact Import Contract (MANDATORY)
In `src/app/(app)/analytics.tsx`:
```typescript
import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useDatabase } from '../../contexts/DatabaseContext';
import { Colors } from '../../theme';
import { kgToLb } from '../../domain/units';
import type { Exercise, SessionSummary, UserProfile } from '../../domain/types';
import type { ExerciseHistoryEntry } from '../../db/repositories/sessionRepository';
import { TrendingUp, Trophy, Dumbbell, Calendar, Flame, History, User } from 'lucide-react-native';

export interface PersonalRecord {
  readonly weightKg: number;
  readonly reps: number;
  readonly achievedAt: string;
}
```

In `src/app/(app)/_layout.tsx`:
```typescript
import React from 'react';
import { Tabs } from 'expo-router';
import { Flame, Calendar, History, TrendingUp, User } from 'lucide-react-native';
import { Colors } from '../../theme';
```

## 3. Exact Database Queries & Shape Handling
```typescript
const { dataLayer, loading: dbLoading } = useDatabase();
if (!dataLayer || dbLoading) {
  return (
    <View style={styles.loadingContainer}>
      <ActivityIndicator size="large" color={Colors.primary} />
    </View>
  );
}

// 1. Current Profile:
const profile = await dataLayer.profiles.find();
if (!profile) return;

// 2. Exercise Catalog (Note: list() takes NO 'isArchived' param, filter in memory if needed):
const allExercises = await dataLayer.exercises.list();

// 3. Completed Sessions (returns SessionSummary[]):
const summaries: SessionSummary[] = await dataLayer.sessions.listHistory(profile.id, {
  limit: 100,
  completedOnly: true,
});

// Calculate Overall Stats from SessionSummary[]:
// NOTE: property is 'workingSetCount', NOT 'totalWorkingSets' or 'summary.totalWorkingSets'!
const totalWorkouts = summaries.length;
const totalVolumeKg = summaries.reduce((sum, s) => sum + (s.totalVolumeKg || 0), 0);
const totalWorkingSets = summaries.reduce((sum, s) => sum + (s.workingSetCount || 0), 0);

// 4. Default Exercise Selection (safe narrowing):
const defaultEx = allExercises.find((e) => e.role === 'compound') ?? (allExercises.length > 0 ? allExercises[0] : null);
const activeExerciseId = selectedExerciseId ?? (defaultEx ? defaultEx.id : null);

// 5. Personal Record & History for selected exercise:
let pr: PersonalRecord | null = null;
let history: ExerciseHistoryEntry[] = [];

if (activeExerciseId) {
  pr = await dataLayer.sessions.personalRecord(profile.id, activeExerciseId);
  history = await dataLayer.sessions.exerciseHistory(profile.id, activeExerciseId, { limit: 20 });
}
```

## 4. UI Layout Requirements (All self-contained in `analytics.tsx`)
1. **Overall Stats Bar (Top)**:
   - Total Workouts (`totalWorkouts`).
   - Total Volume (`profile.preferredUnit === 'lb' ? Math.round(kgToLb(totalVolumeKg)) : Math.round(totalVolumeKg)` with unit).
   - Total Working Sets (`totalWorkingSets`).
2. **Exercise Selector**:
   - Horizontal scrollable chips of exercises, highlighting the currently selected exercise.
3. **Personal Record Card**:
   - Displays best weight (`kg` or `lb`), reps, and formatted date (`new Date(pr.achievedAt).toLocaleDateString()`). If `null`, show "No PR logged yet".
4. **History Progression List**:
   - List of recent performances using `ExerciseHistoryEntry`: Date (`new Date(entry.startedAt).toLocaleDateString()`), Best Set (`entry.bestSetWeightKg` kg × `entry.bestSetReps` reps), Volume (`entry.volumeKg` kg), and Working Sets (`entry.workingSets`).
5. **Empty & Loading States**:
   - `ActivityIndicator` on initial load.
   - Clean empty state if no completed workouts exist.
   - `RefreshControl` with active refresh handler calling the fetch logic.
   - `useFocusEffect` callback to refresh data on screen focus.

## 5. `_layout.tsx` Tab Bar Registration
Register all 5 tabs cleanly:
- `index`: title "Today", icon `<Flame size={size} color={color} />`
- `program`: title "Program", icon `<Calendar size={size} color={color} />`
- `history`: title "History", icon `<History size={size} color={color} />`
- `analytics`: title "Analytics", icon `<TrendingUp size={size} color={color} />`
- `profile`: title "Profile", icon `<User size={size} color={color} />`

## 6. Theme & Dependency Guards (CRITICAL)
- **Colors token list**: ONLY use tokens that exist in `theme/colors.ts`:
  - `Colors.background`
  - `Colors.surface`
  - `Colors.border`
  - `Colors.text`
  - `Colors.textMuted`
  - `Colors.primary`
  - `Colors.primaryForeground`
  - `Colors.destructive` (for error states)
  - DO NOT use `Colors.card`, `Colors.textPrimary`, `Colors.textSecondary`, `Colors.onPrimary`.
- **Icons**: ONLY `lucide-react-native`. NEVER import `@expo/vector-icons` or `date-fns`.
