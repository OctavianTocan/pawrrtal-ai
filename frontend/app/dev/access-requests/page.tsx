import type { Metadata } from 'next';
import { AccessRequestsDevClient } from './AccessRequestsDevClient';

export const metadata: Metadata = {
  title: 'Access Request Banner Dev',
  description: 'Dev-only visual checks for access request banner states.',
};

export default function AccessRequestsDevPage(): React.JSX.Element {
  return <AccessRequestsDevClient />;
}
