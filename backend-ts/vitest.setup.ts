import { addEqualityTesters } from '@effect/vitest';

// Schema.Class / Equal values need custom matchers or assertions fail opaquely.
addEqualityTesters();
