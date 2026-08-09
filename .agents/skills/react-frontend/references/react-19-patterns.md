# React 19 Standards & Design Patterns

React 19 introduces modernized APIs that simplify asynchronous operations, form handling, resource loading, and ref passing.

---

## 1. Actions & Form Handling Hooks

React 19 elevates form submissions and async updates into **Actions**. Instead of managing loading spinners and error states with manual `useState` and `useEffect`, use the action primitives:

### `useActionState`
Manages pending state, errors, and returned results from async form actions.

```tsx
import { useActionState } from 'react';
import { updateUsernameAction } from './actions';

export function UsernameEditor({ currentName }: { currentName: string }) {
  const [state, formAction, isPending] = useActionState(updateUsernameAction, {
    error: null,
    success: false,
  });

  return (
    <form action={formAction}>
      <input name="username" defaultValue={currentName} disabled={isPending} />
      <button type="submit" disabled={isPending}>
        {isPending ? 'Saving...' : 'Save'}
      </button>
      {state.error && <p className="text-red-500">{state.error}</p>}
    </form>
  );
}
```

### `useFormStatus`
Enables child components to read the parent `<form>` status without prop-drilling.

```tsx
import { useFormStatus } from 'react';

export function SubmitButton({ label = 'Submit' }: { label?: string }) {
  const { pending } = useFormStatus();

  return (
    <button type="submit" disabled={pending} className="btn-primary">
      {pending ? 'Processing...' : label}
    </button>
  );
}
```

### `useOptimistic`
Provides instant user feedback by showing an optimistic state while an action is inflight.

```tsx
import { useOptimistic } from 'react';

export function CommentList({ comments, onAddComment }: CommentListProps) {
  const [optimisticComments, addOptimisticComment] = useOptimistic(
    comments,
    (current, newText: string) => [
      ...current,
      { id: 'temp-' + Date.now(), text: newText, isSending: true },
    ]
  );

  async function handleAction(formData: FormData) {
    const text = formData.get('comment') as string;
    addOptimisticComment(text);
    await onAddComment(text);
  }

  return (
    <div>
      <form action={handleAction}>
        <input name="comment" required />
        <SubmitButton label="Post Comment" />
      </form>

      <ul>
        {optimisticComments.map((c) => (
          <li key={c.id} className={c.isSending ? 'opacity-50' : ''}>
            {c.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

---

## 2. Resource Unwrapping with `use()`

The `use()` API reads promises and context dynamically. Unlike traditional hooks, `use()` can be called conditionally and inside loops.

```tsx
import { use, Suspense } from 'react';

function UserProfileDetails({ userPromise }: { userPromise: Promise<UserData> }) {
  const user = use(userPromise); // Unwraps promise, suspends if pending

  return <div>Welcome back, {user.name}!</div>;
}

export function UserSection({ userPromise }: { userPromise: Promise<UserData> }) {
  return (
    <Suspense fallback={<div>Loading user profile...</div>}>
      <UserProfileDetails userPromise={userPromise} />
    </Suspense>
  );
}
```

---

## 3. Direct `ref` Passing

In React 19, `ref` is a standard prop. `forwardRef` is deprecated and no longer needed.

```tsx
interface CustomInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  ref?: React.Ref<HTMLInputElement>;
}

export function CustomInput({ label, ref, ...inputProps }: CustomInputProps) {
  return (
    <label>
      <span>{label}</span>
      <input ref={ref} {...inputProps} />
    </label>
  );
}
```

---

## 4. State Management Strategy

1. **Server State**: Use **TanStack Query (React Query)** or framework Server Actions for caching, revalidation, and fetching external data.
2. **Global Client State**: Use lightweight atomic stores like **Zustand** or **Jotai** for app-wide UI preferences (theme, drawer state, active session).
3. **Local Component State**: Use standard React primitives (`useState`, `useReducer`, `useActionState`) for component-encapsulated UI behavior.

---

## 5. React Compiler & Performance

With the React Compiler enabled in modern React setups:
- Do not manually wrap callbacks in `useCallback` or components in `React.memo` by default.
- Keep components pure, deterministic, and side-effect free in render loops.
- Let automatic memoization handle re-render optimizations.
