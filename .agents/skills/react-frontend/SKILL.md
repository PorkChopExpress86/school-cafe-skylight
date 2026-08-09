---
name: react-frontend
description: >-
  Use this skill when creating, scaffolding, or refactoring modern React frontend applications.
  Provides React 19 standards, strict TypeScript conventions, variable and component naming rules,
  feature-driven project architecture, and modern form/state handling patterns.
---

# React Frontend Application Skill

This skill defines the standards, architectural practices, naming conventions, and modern patterns for building production-grade React frontend applications adhering to React 19 standards.

---

## 🚀 Workflow Steps

### 1. Project Initialization & Architecture Selection
Choose the appropriate framework and project layout based on requirements:
- **Vite + React 19 + TypeScript**: For Single-Page Applications (SPAs) or client-side dashboards.
- **Next.js (App Router)**: For full-stack React applications needing SSR, SSG, or Server Actions.

Follow the [Project Architecture Guide](./references/project-structure.md) to set up a scalable feature-driven folder layout (`src/features/`, `src/components/ui/`, `src/lib/`).

---

## 📐 Framework Standards & Naming Conventions

Enforce consistent naming across the entire codebase:
- **Components**: `PascalCase` (`UserProfileCard.tsx`).
- **Files**: `PascalCase.tsx` for components, `camelCase.ts` for hooks/utilities (`useAuth.ts`, `formatDate.ts`), `kebab-case` for directories (`user-profile/`).
- **Props Interface**: `[ComponentName]Props` (`UserProfileCardProps`).
- **Variables & Functions**: `camelCase` (`submitOrder`, `isPending`).
- **Boolean Flags**: Prefix with `is`, `has`, `can`, `should` (`isActive`, `hasPermission`).
- **Event Handlers**:
  - Prop callbacks: `on[Event]` (`onSelect`, `onFilterChange`).
  - Internal handlers: `handle[Event]` (`handleSelect`, `handleFilterChange`).
- **Constants**: `SCREAMING_SNAKE_CASE` (`MAX_RETRY_COUNT`, `API_BASE_URL`).

See the complete rules in [Naming Conventions & Code Standards](./references/naming-conventions.md).

---

## ⚡ React 19 Core Patterns

Leverage modern React 19 primitives:
1. **Actions & Async State**: Use `useActionState`, `useFormStatus`, and `useOptimistic` for declarative form handling and mutations instead of manual `useState` and `useEffect` loading spinners.
2. **Resource Unwrapping**: Use `use()` to read Promises and Context dynamically.
3. **Ref as a Standard Prop**: Pass `ref` directly as a prop to components (`ref?: React.Ref<T>`). Do not use `forwardRef`.
4. **Automatic Compiler Optimizations**: Avoid manual `useMemo` / `useCallback` micro-optimizations unless mandated by measured bottlenecks; let the React Compiler optimize pure component code.
5. **State Separation**:
   - **Server State**: Managed via TanStack Query (React Query) or Server Actions.
   - **Client App State**: Minimal global state via Zustand or Jotai.
   - **Form State**: Native HTML `FormData` + Actions (`useActionState`).

Read detailed usage examples in [React 19 Patterns](./references/react-19-patterns.md).

---

## 📁 Reference Materials & Examples

- 📖 [Naming Conventions & Standards](./references/naming-conventions.md)
- 📖 [React 19 Features & State Patterns](./references/react-19-patterns.md)
- 📖 [Project Folder Architecture](./references/project-structure.md)
- 💡 [Modern Component Template](./examples/component-template.tsx)

---

## ✅ Quality & Validation Checklist

Before finalizing any React component or application feature:
- [ ] **Type-check**: `npx tsc --noEmit` passes with zero errors.
- [ ] **Lint**: `npx eslint .` passes clean with no unresolved warnings.
- [ ] **Prop Safety**: Component props are typed via explicit interfaces (`[ComponentName]Props`).
- [ ] **Handlers**: Event handlers follow `handleX` (internal) and `onX` (prop) naming.
- [ ] **Form State**: Forms leverage React 19 Actions (`useActionState` / `useFormStatus`) without unneeded `useEffect` syncs.
- [ ] **Styling**: Component styles are modern, responsive, and follow Tailwind CSS or CSS Modules.
