import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

type RunTrigger = "manual" | "periodic" | "shutdown";
type RunOutcome = "success" | "skipped" | "failed" | "timed-out";

type Config = {
	archiveRoot: string;
	intervalMs: number;
	middensBin: string;
	runTimeoutMs: number;
	shutdownTimeoutMs: number;
};

type LastRun = {
	trigger: RunTrigger;
	outcome: RunOutcome;
	startedAt: number;
	finishedAt: number;
	exitCode?: number;
	message: string;
};

const DEFAULT_INTERVAL_MINUTES = 60;
const DEFAULT_RUN_TIMEOUT_MS = 5 * 60 * 1000;
const DEFAULT_SHUTDOWN_TIMEOUT_MS = 20 * 1000;
const MIN_INTERVAL_MINUTES = 1;
const STATUS_KEY = "middens-archive";

export default function (pi: ExtensionAPI) {
	let config: Config | undefined;
	let configError: string | undefined;
	let timer: ReturnType<typeof setInterval> | undefined;
	let running = false;
	let sessionStartedAt = 0;
	let lastStartedAt = 0;
	let lastFinishedAt = 0;
	let lastRun: LastRun | undefined;

	function loadConfig(): Config | undefined {
		configError = undefined;

		const archiveRoot = process.env.MIDDENS_ARCHIVE_ROOT?.trim();
		if (!archiveRoot) {
			return undefined;
		}

		const intervalMinutes = readPositiveNumberEnv(
			"MIDDENS_ARCHIVE_INTERVAL_MINUTES",
			DEFAULT_INTERVAL_MINUTES,
			MIN_INTERVAL_MINUTES,
		);
		if (typeof intervalMinutes === "string") {
			configError = intervalMinutes;
			return undefined;
		}

		const runTimeoutMs = readPositiveNumberEnv("MIDDENS_ARCHIVE_TIMEOUT_MS", DEFAULT_RUN_TIMEOUT_MS, 1_000);
		if (typeof runTimeoutMs === "string") {
			configError = runTimeoutMs;
			return undefined;
		}

		const shutdownTimeoutMs = readPositiveNumberEnv(
			"MIDDENS_ARCHIVE_SHUTDOWN_TIMEOUT_MS",
			DEFAULT_SHUTDOWN_TIMEOUT_MS,
			1_000,
		);
		if (typeof shutdownTimeoutMs === "string") {
			configError = shutdownTimeoutMs;
			return undefined;
		}

		return {
			archiveRoot,
			intervalMs: intervalMinutes * 60 * 1000,
			middensBin: process.env.MIDDENS_ARCHIVE_MIDDENS_BIN?.trim() || "middens",
			runTimeoutMs,
			shutdownTimeoutMs,
		};
	}

	function notify(ctx: ExtensionContext, message: string, level: "info" | "warning" | "error") {
		if (ctx.hasUI) {
			ctx.ui.notify(message, level);
		} else {
			const prefix = level === "error" ? "ERROR" : level === "warning" ? "WARN" : "INFO";
			console.error(`[middens-archive] ${prefix}: ${message}`);
		}
	}

	function setStatus(ctx: ExtensionContext, value: string | undefined) {
		if (ctx.hasUI) {
			ctx.ui.setStatus(STATUS_KEY, value);
		}
	}

	function stopTimer() {
		if (timer) {
			clearInterval(timer);
			timer = undefined;
		}
	}

	function shouldRunConfigured(trigger: RunTrigger, force: boolean, now: number): boolean {
		if (!config) return false;
		if (running) return false;
		if (force) return true;
		const lastActivityAt = Math.max(lastStartedAt, lastFinishedAt, trigger === "shutdown" ? sessionStartedAt : 0);
		return lastActivityAt === 0 || now - lastActivityAt >= config.intervalMs;
	}

	async function runArchive(trigger: RunTrigger, ctx: ExtensionContext, options: { force?: boolean; timeoutMs?: number } = {}) {
		const cfg = config;
		const now = Date.now();
		const force = options.force ?? false;

		if (!cfg) {
			if (configError) {
				notify(ctx, configError, "error");
			} else {
				notify(ctx, "MIDDENS_ARCHIVE_ROOT is unset; Pi session auto-archive is disabled.", "warning");
			}
			return;
		}

		if (running) {
			lastRun = {
				trigger,
				outcome: "skipped",
				startedAt: now,
				finishedAt: now,
				message: "An archive run is already in progress.",
			};
			if (force) notify(ctx, "middens archive is already running; skipped overlapping request.", "warning");
			return;
		}

		if (!shouldRunConfigured(trigger, force, now)) {
			const lastActivityAt = Math.max(lastStartedAt, lastFinishedAt, trigger === "shutdown" ? sessionStartedAt : 0);
			const remainingMs = lastActivityAt === 0 ? cfg.intervalMs : cfg.intervalMs - (now - lastActivityAt);
			lastRun = {
				trigger,
				outcome: "skipped",
				startedAt: now,
				finishedAt: now,
				message: `Debounced; next automatic archive is due in ${formatDuration(remainingMs)}.`,
			};
			return;
		}

		running = true;
		lastStartedAt = now;
		setStatus(ctx, "archiving…");

		const timeoutMs = options.timeoutMs ?? cfg.runTimeoutMs;
		const args = ["archive", "--source", "pi-coding-agent", "--to", cfg.archiveRoot, "--yes"];
		let outcome: RunOutcome = "failed";
		let message = "Archive failed.";
		let exitCode: number | undefined;

		try {
			const result = await pi.exec(cfg.middensBin, args, { timeout: timeoutMs });
			exitCode = result.code;
			if (result.code === 0) {
				outcome = "success";
				message = "Pi session archive completed.";
				if (trigger === "manual") notify(ctx, "Pi session archive completed.", "info");
			} else {
				outcome = result.killed ? "timed-out" : "failed";
				message = result.killed
					? `middens archive timed out after ${formatDuration(timeoutMs)}.`
					: `middens archive failed with exit code ${result.code}.`;
				notify(ctx, message, "error");
			}
		} catch (error) {
			message = error instanceof Error ? error.message : "middens archive failed with an unknown error.";
			notify(ctx, sanitizeError(message), "error");
		} finally {
			const finishedAt = Date.now();
			lastFinishedAt = finishedAt;
			lastRun = {
				trigger,
				outcome,
				startedAt: now,
				finishedAt,
				exitCode,
				message,
			};
			running = false;
			setStatus(ctx, outcome === "success" ? "archive ok" : undefined);
		}
	}

	function configureForSession(ctx: ExtensionContext) {
		stopTimer();
		sessionStartedAt = Date.now();
		config = loadConfig();

		if (!config) {
			if (configError && ctx.hasUI) {
				notify(ctx, configError, "error");
			}
			setStatus(ctx, undefined);
			return;
		}

		setStatus(ctx, `archive every ${formatDuration(config.intervalMs)}`);
		timer = setInterval(() => {
			void runArchive("periodic", ctx);
		}, config.intervalMs);
		if (typeof timer.unref === "function") timer.unref();
	}

	pi.on("session_start", async (_event, ctx) => {
		configureForSession(ctx);
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		stopTimer();
		if (!config) return;
		await runArchive("shutdown", ctx, { timeoutMs: config.shutdownTimeoutMs });
	});

	pi.registerCommand("middens-archive-now", {
		description: "Archive Pi coding-agent session logs with middens now",
		handler: async (_args, ctx) => {
			config = loadConfig();
			await runArchive("manual", ctx, { force: true });
		},
	});

	pi.registerCommand("middens-archive-status", {
		description: "Show middens Pi session archive status",
		handler: async (_args, ctx) => {
			config = loadConfig();
			if (!config) {
				const msg = configError ?? "MIDDENS_ARCHIVE_ROOT is unset; Pi session auto-archive is disabled.";
				notify(ctx, msg, configError ? "error" : "warning");
				return;
			}

			const previousRun = lastRun;
			const last = previousRun
				? `${previousRun.outcome} via ${previousRun.trigger} at ${new Date(previousRun.finishedAt).toISOString()} (${formatDuration(previousRun.finishedAt - previousRun.startedAt)})`
				: "no archive run yet";
			const next = running
				? "currently running"
				: lastFinishedAt === 0
					? "waiting for first interval or /middens-archive-now"
					: `next automatic run in ${formatDuration(Math.max(0, config.intervalMs - (Date.now() - lastFinishedAt)))}`;
			notify(
				ctx,
				`middens archive configured: root=${config.archiveRoot}; interval=${formatDuration(config.intervalMs)}; ${next}; last=${last}`,
				"info",
			);
		},
	});
}

function readPositiveNumberEnv(name: string, defaultValue: number, minValue: number): number | string {
	const raw = process.env[name]?.trim();
	if (!raw) return defaultValue;

	const value = Number(raw);
	if (!Number.isFinite(value) || value < minValue) {
		return `${name} must be a number >= ${minValue}; got ${JSON.stringify(raw)}. Example: ${name}=${defaultValue}`;
	}

	return value;
}

function formatDuration(ms: number): string {
	const safeMs = Math.max(0, Math.round(ms));
	if (safeMs < 1000) return `${safeMs}ms`;
	const seconds = Math.round(safeMs / 1000);
	if (seconds < 60) return `${seconds}s`;
	const minutes = Math.round(seconds / 60);
	if (minutes < 60) return `${minutes}m`;
	const hours = Math.round(minutes / 60);
	return `${hours}h`;
}

function sanitizeError(message: string): string {
	const firstLine = message.split(/\r?\n/, 1)[0]?.trim();
	return firstLine || "middens archive failed.";
}
