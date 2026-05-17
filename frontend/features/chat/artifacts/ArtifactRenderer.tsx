'use client';

/**
 * Wraps json-render's `<Renderer>` with the Pawrrtal catalog + providers.
 *
 * @fileoverview Used by both `<ArtifactCard>` (in-line preview) and
 * `<ArtifactDialog>` (full-screen viewer). Encapsulates the registry +
 * provider plumbing so callers don't repeat them.
 *
 * Also installs the per-artifact {@link ArtifactInteractionScope} so the
 * interactive widgets inside the spec ({@link ActionButtonRenderer},
 * {@link ChoiceGroupRenderer}, etc.) can dispatch user submissions back
 * to the chat surface without knowing about the surrounding container.
 */

import type { Components, Spec } from '@json-render/react';
import { defineRegistry, JSONUIProvider, Renderer } from '@json-render/react';
import type { ReactNode } from 'react';
import type { ChatArtifactPayload } from '../types';
import { artifactCatalog } from './catalog';
import { artifactComponents } from './components';
import { ArtifactInteractionScope } from './interaction-context';

// Registry creation is module-level: the catalog + components are static so
// rebuilding the registry on every render would be pure waste.
// artifactComponents uses BaseComponentProps<any> for loose typing; cast to
// Components<...> here — json-render validates props against catalog schemas.
const { registry } = defineRegistry(artifactCatalog, {
	components: artifactComponents as unknown as Components<typeof artifactCatalog>,
});

interface ArtifactRendererProps {
	artifact: ChatArtifactPayload;
	/**
	 * Fired after a successful interaction dispatch — the dialog uses
	 * this to close itself when the user has answered. Renderers should
	 * NOT depend on this for correctness; treat as polish.
	 */
	onInteractionSubmitted?: () => void;
}

export function ArtifactRenderer({
	artifact,
	onInteractionSubmitted,
}: ArtifactRendererProps): ReactNode {
	return (
		<ArtifactInteractionScope artifactId={artifact.id} onSubmitted={onInteractionSubmitted}>
			<JSONUIProvider registry={registry}>
				{/* Cast because our ChatArtifactPayload.spec has optional props fields;
				    json-render validates the spec at runtime before rendering. */}
				<Renderer spec={artifact.spec as unknown as Spec} registry={registry} />
			</JSONUIProvider>
		</ArtifactInteractionScope>
	);
}
