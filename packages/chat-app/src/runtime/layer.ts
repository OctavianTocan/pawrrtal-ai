/**
 * The application layer — merges every service layer into one root `Layer`
 * that the `ManagedRuntime` is built from. Adding a new service means adding
 * its `*Live` layer here; nothing else changes.
 */
import * as Layer from 'effect/Layer';
import { AppStoreLive, CatalogLive, NavigationLive } from '@/services';

/** Root layer providing the store, catalog, and navigation services. */
export const AppLayer = Layer.mergeAll(AppStoreLive, CatalogLive, NavigationLive);

/** The set of services provided by {@link AppLayer}. */
export type AppServices = Layer.Success<typeof AppLayer>;
