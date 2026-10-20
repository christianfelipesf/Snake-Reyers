// https://github.com/zerodytrash/TikTok-Chat-Reader/blob/main/connectionWrapper.js

const { EventEmitter } = require('events');

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
        this.reconnectWaitMs = 1000;
        this.maxReconnectAttempts = 5;

        this.connection = new TikTokConnectionClass(uniqueId, options || {});

        this.connection.on('streamEnd', () => {
            this.log(`streamEnd event received, giving up connection`);
            this.reconnectEnabled = false;
        });

        this.connection.on('disconnected', () => {
            globalConnectionCount -= 1;
            this.log(`TikTok connection disconnected`);
            this.scheduleReconnect();
        });

        this.connection.on('error', err => {
            this.log(`Error event triggered: ${err.info}, ${err.exception}`);
            console.error(err);
        });
    }

    connect(isReconnect) {
        this.connection
            .connect()
            .then(state => {
                this.log(
                    `${isReconnect ? 'Reconnected' : 'Connected'} to roomId ${
                        state.roomId
                    }, websocket: ${state.upgradedToWebsocket}`,
                );

                globalConnectionCount += 1;

                // Reset reconnect vars
                this.reconnectCount = 0;
                this.reconnectWaitMs = 1000;

                // Client disconnected while establishing connection => drop connection
                if (this.clientDisconnected) {
                    this.connection.disconnect();
                    return;
                }

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
                this.log(`${isReconnect ? 'Reconnect' : 'Connection'} failed, ${err}`);
                if (isReconnect) {
                    // Schedule the next reconnect attempt
                    this.scheduleReconnect(err);
                } else {
                    // Notify client
                    if (
                        err
                            .toString()
                            .includes("Cannot read properties of undefined (reading 'status')")
                    ) {
                        this.emit(
                            'disconnected',
                            'Currently unavailable to reconnect. Please change server.',
                        );
                } else {
                        console.error('Connection error', err);
                        this.emit('disconnected', err?.message || err?.toString?.() || 'Unknown error.');
                        // Falha inicial do Euler/sign server pode ser transitoria.
                        // Antes o wrapper ficava parado para sempre neste estado.
                        this.scheduleReconnect(err);
                    }
                }
            });
    }

    scheduleReconnect(reason) {
        if (!this.reconnectEnabled) {
            return;
        }
        if (this.reconnectCount >= this.maxReconnectAttempts) {
            this.log(`Give up connection, max reconnect attempts exceeded`);
            this.emit('disconnected', `Connection lost. ${reason}`);
            return;
        }

        this.log(`Try reconnect in ${this.reconnectWaitMs}ms`);

        setTimeout(() => {
            if (!this.reconnectEnabled || this.reconnectCount >= this.maxReconnectAttempts) {
                return;
            }

            this.reconnectCount += 1;
            this.reconnectWaitMs *= 2;
            this.connect(true);
        }, this.reconnectWaitMs);
    }

    disconnect() {
        this.log(`Client connection disconnected`);

        this.clientDisconnected = true;
        this.reconnectEnabled = false;

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
