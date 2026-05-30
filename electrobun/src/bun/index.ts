/**
 * Electrobun main process for the Pawrrtal desktop shell.
 *
 * Equivalent of the removed electron/src/main.ts but using Electrobun APIs.
 *
 * Key differences from the Electron shell:
 *
 *   Electron                              Electrobun
 *   ─────────────────────────────────── ──────────────────────────────────────
 *   ipcMain.handle + contextBridge       BrowserView.defineRPC<PawrrtalRPCType>
 *   preload.ts                           src/shared/rpc-types.ts
 *   electron-store                       src/bun/store.ts (JSON file)
 *   app.getPath('home')                  homedir() from node:os
 *   webContents.send('chan', payload)    win.webview.rpc.send.channelName(payload)
 *   ipcMain.on('permissions:respond')    bun.messages.permissionsRespond handler
 *   win.getBounds() + setBounds()        store.get/set('window') — persisted JSON
 *   BrowserWindow.on('closed')           win.on('close') [same pattern]
 *   app.requestSingleInstanceLock()      Electrobun handles automatically
 *
 * @module
 */

import { homedir } from 'node:os';
import path from 'node:path';

import { ApplicationMenu, app, BrowserView, BrowserWindow } from 'electrobun/bun';

import type { PawrrtalRPCType } from '../shared/rpc-types';
import {
	handleFsListDirectory,
	handleFsReadFile,
	handleFsUnwatch,
	handleFsWatchDirectory,
	handleFsWriteFile,
} from './handlers/fs';
import { handleShellKill, handleShellRun, handleShellSpawnStreaming } from './handlers/shell';
import { getMode, resolvePrompt, setMode, setPromptFn } from './permissions';
import { type StartedServer, startNextServer } from './server';
import { createStore } from './store';
import { addRoot, ensureDefaultWorkspaceRoot, listRoots, removeRoot } from './workspace';

// ELECTROBUN_DEV is not reliably propagated in v1.18 — detect dev mode via
// PAWRRTAL_REPO_ROOT, which the 'bun start' script injects.
const isDev = Boolean(process.env.PAWRRTAL_REPO_ROOT);
const remoteAppUrl = resolveRemoteAppUrl(process.env.PAWRRTAL_REMOTE_URL);
const isRemoteMode = remoteAppUrl !== null;

// ─── Window state persistence ────────────────────────────────────────────────
// Restores the previous window size between launches (mirrors Electron shell).

interface WindowState {
	width: number;
	height: number;
}

const windowStore = createStore<{ window: WindowState }>({
	name: 'window',
	defaults: { window: { width: 1280, height: 820 } },
});

const savedWindow = windowStore.get('window');

// Mutable references — assigned after the Next.js server is ready.
let win: BrowserWindow<PawrrtalRPCType> | undefined;
let server: StartedServer | undefined;

function resolveRemoteAppUrl(value: string | undefined): string | null {
	if (!value) return null;
	const parsed = new URL(value);
	if (parsed.protocol !== 'https:') {
		throw new Error('PAWRRTAL_REMOTE_URL must be an https:// URL.');
	}
	if (parsed.hostname === 'localhost' || parsed.hostname.endsWith('.localhost')) {
		throw new Error('PAWRRTAL_REMOTE_URL cannot point at localhost.');
	}
	return parsed.origin;
}

// ─── RPC definition (replaces ipc.ts + preload.ts) ───────────────────────────

const rpc = BrowserView.defineRPC<PawrrtalRPCType>({
	maxRequestTime: 30_000,
	handlers: {
		requests: {
			// ── Desktop helpers ────────────────────────────────────────────
			openExternal: async ({ url }) => {
				if (typeof url !== 'string') return;
				try {
					const parsed = new URL(url);
					if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return;
				} catch {
					return;
				}
				const cmd =
					process.platform === 'darwin'
						? 'open'
						: process.platform === 'win32'
							? 'start'
							: 'xdg-open';
				Bun.spawn([cmd, url], { stdout: 'ignore', stderr: 'ignore' });
			},

			showOpenFolderDialog: async () => {
				// TODO: Electrobun native folder dialog API (dialog.showOpenDialog equivalent).
				// As of v1.18 this can be invoked via the native shell; tracked in
				// https://github.com/blackboardsh/electrobun/issues — return null as stub.
				return null;
			},

			getPlatform: async () => process.platform,
			getVersion: async () => app.version,

			// ── Workspace ─────────────────────────────────────────────────
			workspaceListRoots: async () => listRoots(),
			workspaceAddRoot: async ({ rootPath }) => {
				if (rootPath) return addRoot(rootPath);
				const defaultRoot = path.join(homedir(), 'Pawrrtal-Workspace');
				return addRoot(defaultRoot);
			},
			workspaceRemoveRoot: async ({ rootPath }) => removeRoot(rootPath),

			// ── Filesystem ────────────────────────────────────────────────
			fsReadFile: async ({ filePath }) => handleFsReadFile(filePath),
			fsWriteFile: async ({ filePath, content }) => handleFsWriteFile(filePath, content),
			fsListDirectory: async ({ dirPath }) => handleFsListDirectory(dirPath),
			fsWatchDirectory: async ({ dirPath }) =>
				handleFsWatchDirectory(dirPath, (event) => {
					win?.webview.rpc.send.fsWatchEvent(event);
				}),
			fsUnwatch: async ({ id }) => handleFsUnwatch(id),

			// ── Shell ─────────────────────────────────────────────────────
			shellRun: async (request) => handleShellRun(request),
			shellSpawnStreaming: async (request) =>
				handleShellSpawnStreaming(
					request,
					(event) => {
						win?.webview.rpc.send.shellStream(event);
					},
					(event) => {
						win?.webview.rpc.send.shellStreamEnd(event);
					}
				),
			shellKill: async ({ jobId }) => handleShellKill(jobId),

			// ── Permissions ───────────────────────────────────────────────
			permissionsGetMode: async () => getMode(),
			permissionsSetMode: async ({ mode }) => setMode(mode),
		},

		messages: {
			/**
			 * Webview replies to a pending permission prompt.
			 * In Electron: ipcMain.on('permissions:respond', handler).
			 */
			permissionsRespond: (response) => {
				resolvePrompt(response);
			},
		},
	},
});

// ─── App menu (replaces electron/src/menu.ts) ────────────────────────────────

ApplicationMenu.setApplicationMenu([
	{
		label: 'File',
		submenu: [
			{ label: 'New Chat', accelerator: 'CmdOrCtrl+T', action: 'new-chat' },
			{ type: 'separator' },
			{ label: 'Quit', accelerator: 'CmdOrCtrl+Q', role: 'quit' },
		],
	},
	{
		label: 'Edit',
		submenu: [
			{ label: 'Undo', accelerator: 'CmdOrCtrl+Z', role: 'undo' },
			{ label: 'Redo', accelerator: 'CmdOrCtrl+Shift+Z', role: 'redo' },
			{ type: 'separator' },
			{ label: 'Cut', accelerator: 'CmdOrCtrl+X', role: 'cut' },
			{ label: 'Copy', accelerator: 'CmdOrCtrl+C', role: 'copy' },
			{ label: 'Paste', accelerator: 'CmdOrCtrl+V', role: 'paste' },
			{ label: 'Select All', accelerator: 'CmdOrCtrl+A', role: 'selectAll' },
		],
	},
	{
		label: 'View',
		submenu: [
			{ label: 'Reload', accelerator: 'CmdOrCtrl+R', role: 'reload' },
			{ type: 'separator' },
			{ label: 'Zoom In', accelerator: 'CmdOrCtrl+Plus', role: 'zoomIn' },
			{ label: 'Zoom Out', accelerator: 'CmdOrCtrl+-', role: 'zoomOut' },
			{ label: 'Reset Zoom', accelerator: 'CmdOrCtrl+0', role: 'resetZoom' },
			{ type: 'separator' },
			{
				label: 'Toggle Full Screen',
				accelerator: 'Ctrl+CmdOrCtrl+F',
				role: 'togglefullscreen',
			},
		],
	},
	{
		label: 'Window',
		submenu: [
			{ label: 'Minimize', accelerator: 'CmdOrCtrl+M', role: 'minimize' },
			{ label: 'Zoom', role: 'zoom' },
			{ type: 'separator' },
			{ label: 'Bring All to Front', role: 'front' },
		],
	},
]);

// ─── Startup ──────────────────────────────────────────────────────────────────

if (!isRemoteMode) {
	ensureDefaultWorkspaceRoot();
}

// Open the splash window immediately — views://splash/index.html is a proper
// secure context (crypto.subtle works), unlike data: URLs.
win = new BrowserWindow({
	title: 'Pawrrtal',
	url: 'views://splash/index.html',
	frame: { width: savedWindow.width, height: savedWindow.height },
	// hiddenInset: traffic lights float over the content area.
	// trafficLightOffset moves them down so they sit inside the nav bar.
	titleBarStyle: 'hiddenInset',
	trafficLightOffset: { x: 10, y: 16 },
	...(isRemoteMode ? {} : { rpc }),
});

if (!isRemoteMode) {
	setPromptFn((request) => {
		win?.webview.rpc.send.permissionsPrompt(request);
	});
}

// ─── Drag region + traffic-light safe zone injection ────────────────────────
// Injects a <style> tag directly using -webkit-app-region: drag so the
// title bar is draggable without relying on Electrobun's class-based preload,
// which can race against the webview's own preload script execution.
//
// Also injects --eb-traffic-light-h (CSS var) so the frontend can push its
// header content below the macOS traffic-light buttons without hard-coding
// a pixel value. The value matches trafficLightOffset.y + button height (~28px).
//
// Re-injected on every navigation to survive Next.js soft-nav route changes.

const TRAFFIC_LIGHT_SAFE_H = 44; // px — trafficLightOffset.y(16) + button(28)

const INJECT_DRAG_REGION = `
(function () {
  var prev = document.getElementById('__eb_drag');
  if (prev) prev.remove();
  var s = document.createElement('style');
  s.id = '__eb_drag';
  s.textContent = [
    /* Make the top nav bar the window drag handle. */
    'header, nav, [role="navigation"] { -webkit-app-region: drag; }',
    /* Everything inside must be explicitly no-drag so clicks still work. */
    'header *, nav *, [role="navigation"] * { -webkit-app-region: no-drag; }',
    /* Traffic-light safe-zone variable — frontend reads this to add padding. */
    ':root { --eb-traffic-light-h: ${TRAFFIC_LIGHT_SAFE_H}px; }',
    /* Push header content below the traffic lights. */
    'header { padding-top: max(0px, calc(var(--eb-traffic-light-h, 0px) - 1rem)); }',
  ].join(' ');
  document.head.appendChild(s);
})();
`;

function injectDragRegion() {
	win?.webview.executeJavascript(INJECT_DRAG_REGION);
}

if (!isRemoteMode) {
	win.webview.on('did-navigate', () => {
		injectDragRegion();
	});
	win.webview.on('did-navigate-in-page', () => {
		injectDragRegion();
	});
}

// ─── Graceful shutdown ─────────────────────────────────────────────────────
// Kill the spawned Next.js server when the window closes to avoid ghost
// processes lingering after the app quits (mirrors Electron shell behaviour).

win.on('close', async () => {
	await server?.stop().catch(() => undefined);
});

// Handle custom menu actions.
ApplicationMenu.on('application-menu-clicked', (event: unknown) => {
	const { action } = event as { action: string };
	if (action === 'new-chat') {
		win?.webview.rpc?.send.menuNewChat({});
	}
});

// Start frontend + backend, then navigate the splash to the real URL.
if (remoteAppUrl) {
	win.webview.loadURL(remoteAppUrl);
} else {
	startNextServer({ isDev })
		.then((started) => {
			server = started;
			win?.webview.loadURL(started.url);
		})
		.catch((err: unknown) => {
			const reason = err instanceof Error ? err.message : String(err);
			console.error('[electrobun] startup failed:', reason);
			process.exit(1);
		});
}
