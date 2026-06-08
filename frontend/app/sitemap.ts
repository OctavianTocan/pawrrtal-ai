/**
 * Sitemap entries for the public docs surface (`/docs/**`) plus the
 * top-level docs landing. The app surfaces (`/`, `/login`, `/signup`,
 * `/(app)/**`) are deliberately excluded — they are private to
 * authenticated users.
 */

import type { MetadataRoute } from 'next';
import { handbookSource, productSource } from '@/lib/source';

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://pawrrtal.octaviantocan.com';

/**
 * Generates sitemap entries for `/docs` + every handbook + product page.
 *
 * @returns the sitemap entries
 */
export default function sitemap(): MetadataRoute.Sitemap {
	const handbookEntries: MetadataRoute.Sitemap = handbookSource.getPages().map((page) => ({
		url: `${BASE_URL}${page.url}`,
		lastModified: new Date(),
		changeFrequency: 'weekly',
		priority: 0.7,
	}));

	const productEntries: MetadataRoute.Sitemap = productSource.getPages().map((page) => ({
		url: `${BASE_URL}${page.url}`,
		lastModified: new Date(),
		changeFrequency: 'weekly',
		priority: 0.8,
	}));

	return [
		{
			url: `${BASE_URL}/docs`,
			lastModified: new Date(),
			changeFrequency: 'monthly',
			priority: 0.9,
		},
		...handbookEntries,
		...productEntries,
	];
}
