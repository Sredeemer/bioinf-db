# TypeScript & Frontend Standards

This guide outlines standards for the Next.js frontend (`/web`), interactive UI components, MapLibre visualization layers, and client-side TypeScript development.

---

## 1. Toolchain & Strict TypeScript Configuration

- **TypeScript Version**: **5.4+** in full strict mode.
- **Node.js**: **20+ LTS** (or `bun`).
- **Linter & Formatter**: ESLint (`@typescript-eslint/recommended-type-checked`) + Prettier.

### `tsconfig.json` Compiler Requirements
Ensure the following compiler flags are enabled in `web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "noFallthroughCasesInSwitch": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### Type Safety Rules
- **No `any`**: The use of `any` is forbidden. Use `unknown` and perform narrowing with type guards.
- **Explicit Component Props**: Every React component must define an explicit interface or type for its props:
  ```typescript
  interface DatasetCardProps {
    readonly id: string;
    readonly title: string;
    readonly domain: "bacteria" | "virus" | "veterinary" | "plant" | "parasite" | "metagenome";
    readonly countries: readonly string[];
    readonly isVerifiedAfrican: boolean;
  }
  ```

---

## 2. Next.js 15+ App Router Architecture

### React Server Components (RSC) by Default
- All pages and components are **Server Components** by default.
- **Use `"use client"` sparingly**: Only introduce Client Components at the leaves of the component tree where user interaction, local state (`useState`), browser APIs (DOM, WebGL, MapLibre), or lifecycle hooks (`useEffect`) are required.

```typescript
// src/app/datasets/[owner]/[name]/page.tsx (Server Component)
import { notFound } from "next/navigation";
import { fetchDatasetMetadata } from "@/lib/api/datasets";
import { DatasetHeader } from "@/components/dataset/DatasetHeader";
import { InteractiveFileBrowser } from "@/components/dataset/InteractiveFileBrowser"; // Client Component

interface PageProps {
  params: Promise<{ owner: string; name: string }>;
}

export default async function DatasetPage({ params }: PageProps) {
  const { owner, name } = await params;
  const dataset = await fetchDatasetMetadata(owner, name);

  if (!dataset) {
    notFound();
  }

  return (
    <main className="dataset-container">
      <DatasetHeader dataset={dataset} />
      <InteractiveFileBrowser initialTree={dataset.rootTree} repoId={dataset.id} />
    </main>
  );
}
```

### Route Handlers & Server Actions
- Server components fetch directly from the FastAPI hub backend using typed fetch clients.
- Pass authentication cookies / bearer tokens through server-side request headers.
- Implement `loading.tsx` skeletons and `error.tsx` error boundaries for all dynamic routes.

---

## 3. Styling & Modern Web Aesthetics

### Vanilla CSS & Design Tokens
In accordance with our architectural decisions:
- Use **Vanilla CSS** with CSS Modules (`*.module.css`) to guarantee maximum control, high performance, and zero bundle-bloat.
- All styles must derive from global design tokens declared in `src/styles/tokens.css`:

```css
/* src/styles/tokens.css */
:root {
  /* Color Palette (African Earth & High-Tech Accents) */
  --color-bg-primary: #0a0e14;
  --color-bg-secondary: #121820;
  --color-bg-card: rgba(26, 34, 46, 0.7);
  --color-border: rgba(255, 255, 255, 0.1);
  --color-border-hover: rgba(56, 189, 248, 0.4);

  --color-text-primary: #f8fafc;
  --color-text-secondary: #94a3b8;
  --color-text-muted: #64748b;

  --color-accent-amber: #f59e0b;
  --color-accent-emerald: #10b981;
  --color-accent-cyan: #06b6d4;

  /* Typography */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Glassmorphism & Elevations */
  --backdrop-blur: blur(12px);
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-glow: 0 0 20px -5px rgba(6, 182, 212, 0.25);

  /* Transitions */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-normal: 250ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

### Premium Visual Aesthetics & Micro-interactions
- Dark-mode first design with subtle glassmorphic card overlays (`backdrop-filter: var(--backdrop-blur)`).
- Fluid hover transformations (`transform: translateY(-2px)`) and glow focus states.
- Responsive layouts built via CSS Grid and Flexbox with container queries where appropriate.

---

## 4. MapLibre GL & Geospatial Integration

Because MapLibre GL relies on client-side WebGL context:
1. **Dynamic Loading**: Dynamically import the map component in Next.js with `ssr: false`:
   ```typescript
   import dynamic from "next/dynamic";

   export const AfricaSampleMap = dynamic(
     () => import("@/components/map/AfricaSampleMap").then((m) => m.AfricaSampleMap),
     {
       ssr: false,
       loading: () => <div className="map-skeleton" aria-label="Loading map..." />,
     }
   );
   ```
2. **Self-Hosted PMTiles Protocol**: Register the PMTiles protocol handler before instantiating map sources:
   ```typescript
   import * as pmtiles from "pmtiles";
   import maplibregl from "maplibre-gl";

   const protocol = new pmtiles.Protocol();
   maplibregl.addProtocol("pmtiles", protocol.tile);
   ```
3. **GeoJSON Clustering**: Render sample clusters with performance optimization (disable unneeded animations on large point clouds).

---

## 5. Accessibility (a11y) Standards

Every interactive element and page must comply with **WCAG 2.1 Level AA**:
- **Semantic Tags**: Use proper heading hierarchy (`<h1>` unique per page, followed by `<h2>`, `<h3>`).
- **Interactive Targets**: Minimum tap target of 44×44px for buttons and touch targets.
- **Focus Rings**: Never set `outline: none` without providing an accessible `:focus-visible` ring:
  ```css
  button:focus-visible {
    outline: 2px solid var(--color-accent-cyan);
    outline-offset: 2px;
  }
  ```
- **Color Contrast**: Verify all text against its background with a minimum 4.5:1 ratio for normal text and 3:1 for large text.
- **Screen Reader Announcements**: Use `aria-live="polite"` for search result counters and asynchronous state changes.

---

## 6. Testing Frontend Components

- **Unit / Component Tests**: Use **Vitest** + **React Testing Library**:
  ```typescript
  import { render, screen } from "@testing-library/react";
  import { DatasetCard } from "./DatasetCard";

  test("renders dataset title and verified badge", () => {
    render(
      <DatasetCard
        id="ds-1"
        title="Klebsiella isolates Nigeria"
        domain="bacteria"
        countries={["NG"]}
        isVerifiedAfrican={true}
      />
    );
    expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Klebsiella isolates Nigeria");
    expect(screen.getByLabelText("Verified African Dataset")).toBeInTheDocument();
  });
  ```
- **End-to-End Tests**: Automated with **Playwright** (`/web/e2e`), testing search navigation, filter synchronization with the Africa map, and gated access requests.
