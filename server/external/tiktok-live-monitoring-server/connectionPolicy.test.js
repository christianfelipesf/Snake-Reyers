'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    connectionFailurePolicy,
    genericRetryDelayMs,
} = require('./connectionPolicy');

test('uses Euler retryAfter for signature rate limits', () => {
    const now = Date.parse('2026-10-20T03:00:00.000Z');
    const policy = connectionFailurePolicy({
        name: 'SignatureRateLimitError',
        reason: 'Rate Limited',
        message: '(rate_limit_account_hour) Too many connections started',
        retryAfter: 125_000,
    }, now);

    assert.equal(policy.rateLimited, true);
    assert.equal(policy.code, 'rate_limit_account_hour');
    assert.equal(policy.retryAfterSeconds, 125);
    assert.equal(policy.retryAtEpochMs, now + 125_000);
});

test('uses a one-hour fallback for an hourly limit without headers', () => {
    const now = Date.parse('2026-10-20T03:00:00.000Z');
    const policy = connectionFailurePolicy(
        new Error('SignatureRateLimitError rate_limit_account_hour'),
        now,
    );

    assert.equal(policy.rateLimited, true);
    assert.equal(policy.retryAfterSeconds, 3600);
});

test('generic reconnects are slow and bounded', () => {
    assert.deepEqual(
        [0, 1, 2, 3].map(genericRetryDelayMs),
        [15_000, 45_000, 120_000, 120_000],
    );
});
