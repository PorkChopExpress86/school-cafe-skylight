# React Application Project Architecture

Organizing a React frontend by features rather than raw file types keeps code modular, collocated, and easy to scale.

---

## Feature-Driven Folder Layout (Recommended)

Below is the standard enterprise-ready feature-based structure ("Bulletproof React" pattern):

```text
src/
├── assets/                  # Public assets, images, SVG icons
├── components/              # Shared, generic UI components (Buttons, Inputs, Modals)
│   └── ui/
│       ├── Button.tsx
│       ├── Input.tsx
│       └── Modal.tsx
├── features/                # Domain-specific feature modules
│   ├── auth/                # Authentication feature module
│   │   ├── api/             # Feature API calls / hooks
│   │   │   └── loginUser.ts
│   │   ├── components/      # Feature-specific UI components
│   │   │   ├── LoginForm.tsx
│   │   │   └── AuthProvider.tsx
│   │   ├── hooks/           # Feature-specific custom hooks
│   │   ├── types/           # Feature TypeScript definitions
│   │   │   └── auth.types.ts
│   │   └── index.ts         # Public API export barrel for the feature
│   └── dashboard/
├── hooks/                   # App-wide global custom hooks (e.g. useDebounce, useLocalStorage)
├── lib/                     # Configured instances of 3rd-party libraries (queryClient, axios, zustand)
├── routes/ or app/          # Application routing definitions or Next.js App Router pages
├── styles/                  # Global CSS reset, design tokens, Tailwind directives
├── types/                   # App-wide shared TypeScript interfaces
└── utils/                   # Pure helper utilities (date formatting, string helpers)
```

---

## Colocation Rule

Keep items as close to where they are used as possible:
- If a component is only used within a single feature (`features/auth`), place it inside `features/auth/components/`.
- If a component is generic and reused across multiple features (e.g. `Button`, `Dialog`), move it to `components/ui/`.
- Keep component styles (`.module.css`), tests (`.test.tsx`), and types co-located or adjacent to the component file.

---

## Public Barrel Exports (`index.ts`)

Each feature module should expose a clear public interface via `index.ts`. Internal implementation details remain encapsulated inside the feature directory:

```ts
// src/features/auth/index.ts
export { LoginForm } from './components/LoginForm';
export { useAuth } from './hooks/useAuth';
export type { UserSession } from './types/auth.types';
```
