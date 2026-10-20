// https://github.com/zerodytrash/TikTok-Chat-Reader/blob/main/connectionWrapper.js

const { EventEmitter } = require('events');
const {
    GENERIC_RETRY_DELAYS_MS,
    connectionFailurePolicy,
    genericRetryDelayMs,
} = require('./connectionPolicy');

let globalConnectionCount = 0;
const connector = require('tiktok-live-connector');
const TikTokConnectionClass = connector.TikTokLiveConnection || connector.WebcastPushConnection;

if (!TikTokConnectionClass) {
    throw new Error('Nenhuma classe de conexao TikTok compativel foi encontrada.');
}

class TikTokConnectionWrapper extends EventEmitter {
    constructor(uniqueId, options, enableLog) {
        super();

        this.uniqueId = uniqueId;
        this.enableLog = enableLog;

        // Connection State
        this.clientDisconnected = false;
        this.reconnectEnabled = true;
        this.reconnectCount = 0;
        this.maxReconnectAttempts = GENERIC_RETRY_DELAYS_MS.length;
        this.reconnectTimer = null;
        this.isConnecting = false;
        this.countedConnection = false;

        this.connection = new TikTokConnectionClass(uniqueId, options || {});

        this.connection.on('streamEnd', () => {
            this.log(`streamEnd event received, giving up connection`);
            this.reconnectEnabled = false;
        });

        this.connection.on('disconnected', () => {
            if (this.countedConnection) {
                globalConnectionCount = Math.max(0, globalConnectionCount - 1);
                this.countedConnection = false;
            }
            this.log(`TikTok connection disconnected`);
            if (!this.clientDisconnected && this.reconnectEnabled) {
                const detail = {
                    message: 'TikTok connection disconnected.',
                    rateLimited: false,
                };
                this.emit('disconnected', detail);
                this.scheduleReconnect(detail);
            }
        });

        this.connection.on('error', err => {
            this.log(`Error event triggered: ${err.info}, ${err.exception}`);
            console.error(err);
        });
    }

    connect(isReconnect) {
        if (this.isConnecting || this.clientDisconnected || !this.reconnectEnabled) {
            return Promise.resolve();
        }

        this.isConnecting = true;
        return this.connection
            .connect()
            .then(state => {
                this.isConnecting = false;
                this.log(
                    `${isReconnect ? 'Reconnected' : 'Connected'} to roomId ${
                        state.roomId
                    }, websocket: ${state.upgradedToWebsocket}`,
                );

                // Client disconnected while establishing connection => drop connection
                if (this.clientDisconnected) {
                    this.connection.disconnect();
                    return;
                }

                if (!this.countedConnection) {
                    globalConnectionCount += 1;
                    this.countedConnection = true;
                }

                this.reconnectCount = 0;
                this.clearReconnectTimer();

                // Notify client. A reconexao tambem precisa publicar
                // "connected", senao o servidor Socket.IO continua
                // marcando listening=false mesmo apos recuperar.
                if (!isReconnect) {
                    const roomInfo = this.connection.roomInfo || state.roomInfo || {};
                    this.emit('roomInfo', JSON.stringify(roomInfo));
                }
                this.emit('connected', state);
            })
            .catch(err => {
                this.isConnecting = false;
                this.log(`${isReconnect ? 'Reconnect' : 'Connection'} failed, ${err}`);
                const policy = connectionFailurePolicy(err);

                if (
                    policy.message.includes(
                        "Cannot read properties of undefined (reading 'status')",
                    )
                ) {
                    policy.message = 'Currently unavailable to reconnect. Please change server.';
                }

                console.error('Connection error', err);
                this.emit('disconnected', policy);
                this.scheduleReconnect(policy);
            });
    }

    scheduleReconnect(reason = {}) {
        if (!this.reconnectEnabled || this.clientDisconnected || this.reconnectTimer) {
            return;
        }

        const rateLimited = Boolean(reason?.rateLimited);
        if (!rateLimited && this.reconnectCount >= this.maxReconnectAttempts) {
            this.log(`Give up connection, max reconnect attempts exceeded`);
            this.emit('disconnected', {
                message: `Connection lost. ${reason?.message || reason}`,
                code: 'reconnect_attempts_exhausted',
                rateLimited: false,
            });
            return;
        }

        const delayMs = rateLimited
            ? Math.max(1_000, Number(reason.retryDelayMs) || 0)
            : genericRetryDelayMs(this.reconnectCount);

        this.log(`Try reconnect in ${delayMs}ms`);

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (!this.reconnectEnabled || this.clientDisconnected) {
                return;
            }

            if (!rateLimited) {
                this.reconnectCount += 1;
            }
            this.connect(true);
        }, delayMs);
    }

    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }

    disconnect() {
        this.log(`Client connection disconnected`);

        this.clientDisconnected = true;
        this.reconnectEnabled = false;
        this.clearReconnectTimer();

        const isConnected =
            typeof this.connection.isConnected === 'boolean'
                ? this.connection.isConnected
                : Boolean(this.connection.state && this.connection.state.isConnected);

        if (isConnected && typeof this.connection.disconnect === 'function') {
            this.connection.disconnect();
        }
    }

    log(logString) {
        if (this.enableLog) {
            console.log(`WRAPPER @${this.uniqueId}: ${logString}`);
        }
    }
}

module.exports = {
    TikTokConnectionWrapper,
    getGlobalConnectionCount: () => {
        return globalConnectionCount;
    },
};
