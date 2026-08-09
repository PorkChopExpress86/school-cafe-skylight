# React Naming Conventions & Coding Standards

Consistent naming ensures codebase clarity, maintainability, and seamless team collaboration.

---

## 1. File & Directory Naming

| Category | Format | Example |
| :--- | :--- | :--- |
| **React Components** | `PascalCase.tsx` | `UserProfileCard.tsx`, `NavigationMenu.tsx` |
| **Custom Hooks** | `camelCase.ts` | `useAuth.ts`, `useMediaQuery.ts` |
| **Utilities & Helpers** | `camelCase.ts` | `formatCurrency.ts`, `validators.ts` |
| **Feature Directories** | `kebab-case` | `user-profile/`, `shopping-cart/` |
| **Styles (CSS Modules)** | `PascalCase.module.css` | `UserProfileCard.module.css` |
| **Unit Tests** | `[TargetName].test.tsx` | `UserProfileCard.test.tsx` |

---

## 2. Component & Prop Naming

### Components
- Always use `PascalCase` for component declarations and export names.
- Name components as nouns or noun phrases representing what they render.

```tsx
// Good
export function ShoppingCartList() { ... }

// Avoid
export function shoppingCart() { ... }
export function RenderCart() { ... }
```

### Props Interfaces
- Name prop interfaces using `[ComponentName]Props`.
- Export prop interfaces alongside the component if re-used.

```tsx
export interface UserProfileCardProps {
  userId: string;
  avatarUrl?: string;
  isActive?: boolean;
  onUpdateStatus?: (newStatus: string) => void;
}
```

---

## 3. Variables, Functions & Booleans

### Variables & Functions
- Use `camelCase` for local variables, state variables, and function names.

```tsx
const activeTab = 'overview';
const [itemCount, setItemCount] = useState<number>(0);

function calculateTotalPrice(items: CartItem[]): number { ... }
```

### Boolean Variables & Props
- Prefix boolean variables, state, and props with boolean indicators (`is`, `has`, `can`, `should`).

```tsx
// Good
const isLoading = false;
const hasPermission = true;
const canEdit = false;
const shouldRefresh = true;

// Avoid
const loading = false;
const permission = true;
```

---

## 4. Event Handlers

Distinguish between internal event handlers and external prop callbacks:

- **Internal Event Handlers**: Prefix with `handle` followed by the event or action (`handleClick`, `handleSubmit`, `handleNameChange`).
- **Callback Props**: Prefix with `on` followed by the event or action (`onClick`, `onSubmit`, `onNameChange`).

```tsx
interface SearchInputProps {
  onSearch: (query: string) => void;
}

export function SearchInput({ onSearch }: SearchInputProps) {
  const [query, setQuery] = useState('');

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setQuery(event.target.value);
  };

  const handleFormSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSearch(query);
  };

  return (
    <form onSubmit={handleFormSubmit}>
      <input value={query} onChange={handleInputChange} />
      <button type="submit">Search</button>
    </form>
  );
}
```

---

## 5. Constants & Configuration

- Use `SCREAMING_SNAKE_CASE` for global, immutable constants or configuration values.

```tsx
export const API_TIMEOUT_MS = 5000;
export const DEFAULT_PAGE_SIZE = 20;
export const SUPPORTED_LOCALES = ['en-US', 'es-ES', 'fr-FR'] as const;
```

---

## 6. Custom Hooks

- Custom hook names MUST begin with `use` in `camelCase`.
- Hooks must return an object or a tuple depending on consumption ergonomics.

```tsx
// Tuple (when 2 related items, like useState)
export function useToggle(initialState = false): [boolean, () => void] { ... }

// Object (when 3+ items or named properties)
export function useUserSession() {
  return { user, isLoading, error, logout };
}
```
