// Component layer (stateful) — default import for most consumers
export { AccessRequestBanner } from './AccessRequestBanner';

// View layer (stateless) — exported for Storybook stories and isolated tests
export { AccessRequestBannerView } from './AccessRequestBannerView';

export type {
  AccessRequest,
  AccessRequestBannerProps,
  AccessRequestBannerViewProps,
} from './types';
