import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { StepMessaging } from './step-messaging';

vi.mock('next/navigation', () => ({
	useRouter: () => ({
		push: vi.fn(),
		replace: vi.fn(),
		back: vi.fn(),
		forward: vi.fn(),
		refresh: vi.fn(),
		prefetch: vi.fn(),
	}),
	usePathname: () => '/',
	useSearchParams: () => new URLSearchParams(),
}));

// Mock useAuthedFetch to prevent the transitive useRouter() call chain
// (TelegramConnectDialog -> useTelegramBinding -> useAuthedQuery -> useAuthedFetch -> useRouter).
const { mockAuthedFetch } = vi.hoisted(() => ({
	mockAuthedFetch: vi.fn().mockResolvedValue({
		ok: true,
		status: 200,
		json: async () => [],
		text: async () => '[]',
	}),
}));
vi.mock('@/hooks/use-authed-fetch', () => ({
	useAuthedFetch: () => mockAuthedFetch,
}));

vi.mock('@/lib/channels', () => ({
	listChannels: vi.fn().mockResolvedValue([]),
}));

function createWrapper(): React.ComponentType<{ children: React.ReactNode }> {
	const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	return function Wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

describe('StepMessaging', () => {
	it('renders every channel as a Connect row', () => {
		const { getByText } = render(
			<StepMessaging
				onFinish={vi.fn()}
				onPatch={vi.fn()}
				profile={{ connectedChannels: [] }}
			/>,
			{ wrapper: createWrapper() }
		);
		expect(getByText('Connect Slack')).toBeTruthy();
		expect(getByText('Connect Telegram')).toBeTruthy();
		expect(getByText('Connect WhatsApp')).toBeTruthy();
		expect(getByText('Connect iMessage')).toBeTruthy();
	});

	it('disables Continue until at least one channel is connected', () => {
		const Wrapper = createWrapper();
		const { getByRole, rerender } = render(
			<StepMessaging
				onFinish={vi.fn()}
				onPatch={vi.fn()}
				profile={{ connectedChannels: [] }}
			/>,
			{ wrapper: Wrapper }
		);
		const continueButton = getByRole('button', {
			name: 'Finish messaging setup',
		}) as HTMLButtonElement;
		expect(continueButton.disabled).toBe(true);

		rerender(
			<StepMessaging
				onFinish={vi.fn()}
				onPatch={vi.fn()}
				profile={{ connectedChannels: ['slack'] }}
			/>
		);
		expect(
			(getByRole('button', { name: 'Finish messaging setup' }) as HTMLButtonElement).disabled
		).toBe(false);
	});

	it('toggles a channel on Connect click and emits the new connectedChannels list', async () => {
		const onPatch = vi.fn();
		const user = userEvent.setup();
		const { getAllByRole } = render(
			<StepMessaging
				onFinish={vi.fn()}
				onPatch={onPatch}
				profile={{ connectedChannels: [] }}
			/>,
			{ wrapper: createWrapper() }
		);
		const buttons = getAllByRole('button', { name: 'Connect' });
		const first = buttons[0];
		if (!first) throw new Error('expected at least one Connect button');
		await user.click(first);
		expect(onPatch).toHaveBeenCalledWith({ connectedChannels: ['slack'] });
	});

	it('fires onFinish when Continue is clicked while at least one channel is connected', async () => {
		const onFinish = vi.fn();
		const user = userEvent.setup();
		const { getByRole } = render(
			<StepMessaging
				onFinish={onFinish}
				onPatch={vi.fn()}
				profile={{ connectedChannels: ['slack'] }}
			/>,
			{ wrapper: createWrapper() }
		);
		await user.click(getByRole('button', { name: 'Finish messaging setup' }));
		expect(onFinish).toHaveBeenCalled();
	});
});
