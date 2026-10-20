'use strict';

const GENERIC_RETRY_DELAYS_MS = [15_000, 45_000, 120_000];
const DEFAULT_RATE_LIMIT_MS = 10 * 60_000;
const DEFAULT_HOURLY_RATE_LIMIT_MS = 60 * 60_000;

function errorText(error) {
    return String(error?.message || error?.toString?.() || error || 'Unknown error.');
}

function errorCode(error, text = errorText(error)) {
    const explicit = String(error?.code || error?.limitLabel || '').trim();
    if (explicit) return explicit;

    const match = String(text).match(/rate_limit_[a-z0-9_]+/i);
    return match ? match[0].toLowerCase() : '';
}

function rateLimitDelayMs(error, nowMs = Date.now()) {
    const text = errorText(error);
    const code = errorCode(error, text);
    const retryAfter = Number(error?.retryAfter || 0);
    const resetTime = Number(error?.resetTime || 0);
    const fallback = code === 'rate_limit_account_hour'
        ? DEFAULT_HOURLY_RATE_LIMIT_MS
        : DEFAULT_RATE_LIMIT_MS;

    const candidates = [
        Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : 0,
        Number.isFinite(resetTime) && resetTime > nowMs ? resetTime - nowMs : 0,
    ];
    const suppliedDelay = Math.max(...candidates);

    return suppliedDelay > 0 ? suppliedDelay : fallback;
}

function connectionFailurePolicy(error, nowMs = Date.now()) {
    const message = errorText(error);
    const code = errorCode(error, message);
    const rateLimited = (
        error?.name === 'SignatureRateLimitError'
        || error?.reason === 'Rate Limited'
        || /SignatureRateLimitError|Rate Limited|rate_limit_/i.test(message)
    );

    if (!rateLimited) {
        return {
            rateLimited: false,
            code,
            message,
        };
    }

    const retryDelayMs = rateLimitDelayMs(error, nowMs);
    const retryAtEpochMs = nowMs + retryDelayMs;

    return {
        rateLimited: true,
        code: code || 'signature_rate_limit',
        message,
        retryDelayMs,
        retryAfterSeconds: Math.max(1, Math.ceil(retryDelayMs / 1000)),
        retryAtEpochMs,
        retryAt: new Date(retryAtEpochMs).toISOString(),
    };
}

function genericRetryDelayMs(attemptIndex) {
    return GENERIC_RETRY_DELAYS_MS[Math.min(
        Math.max(0, Number(attemptIndex) || 0),
        GENERIC_RETRY_DELAYS_MS.length - 1,
    )];
}

module.exports = {
    GENERIC_RETRY_DELAYS_MS,
    connectionFailurePolicy,
    genericRetryDelayMs,
};
