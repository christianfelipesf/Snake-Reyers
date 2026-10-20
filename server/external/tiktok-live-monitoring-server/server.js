const express = require('express');
const { Server } = require('socket.io');
const http = require('http');
const { Readable } = require('stream');
const { TikTokConnectionWrapper } = require('./connectionWrapper');
const cors = require('cors');
const { reverseInPlace } = require('./function');
const { SocksProxyAgent } = require('socks-proxy-agent');
const path = require('path');

const PORT = Number(process.env.TIKTOK_MONITOR_PORT || 2618);
const HOST = String(process.env.TIKTOK_MONITOR_HOST || '127.0.0.1').trim();
const TOR_PROXY = String(
    process.env.SNAKE_REYERS_TOR_PROXY || 'socks5h://127.0.0.1:9050',
).trim();
const TOR_MONITOR_REQUIRED =
    String(process.env.SNAKE_REYERS_REQUIRE_TOR_MONITOR || '1').toLowerCase() !== '0';
const TOR_WRAPPED =
    process.env.SNAKE_REYERS_TOR_WRAPPED === '1' ||
    process.env.COBRINHA_TIKTOK_MONITOR_WRAPPED === '1' ||
    String(process.env.LD_PRELOAD || '').toLowerCase().includes('torsocks');

if (TOR_MONITOR_REQUIRED && !TOR_WRAPPED && !TOR_PROXY) {
    console.error('TikTok monitor bloqueado: Tor e obrigatorio para ler o chat.');
    process.exit(88);
}

function createTorOptions() {
    if (!TOR_MONITOR_REQUIRED && !TOR_PROXY) return {};

    const agent = new SocksProxyAgent(TOR_PROXY, {
        keepAlive: true,
    });

    return {
        webClientOptions: {
            agent: {
                http: agent,
                https: agent,
            },
        },
        wsClientOptions: {
            agent,
        },
    };
}

const app = express();
const server = http.createServer(app);
const ws = new Server(server, { cors: { origin: '*' } });

app.use(cors());
app.use(express.json({ limit: '64kb' }));
app.use(express.static(path.join(__dirname, 'public')));

let usernames = [];
let activeListenWrapper = null;

function serializeEvent(data) {
    return JSON.stringify(data, (_key, value) =>
        typeof value === 'bigint' ? value.toString() : value,
    );
}

function emitEvent(socket, eventName, data) {
    try {
        socket.emit(eventName, serializeEvent(data));
    } catch (error) {
        const message = `${eventName}: ${error?.message || error}`;
        console.error(`Falha ao serializar evento TikTok: ${message}`);
        socket.emit(
            'data-monitor-diagnostic',
            JSON.stringify({ event: eventName, message }),
        );
    }
}

ws.on('connection', socket => {
    console.log('New client connected');
    let tiktokConnectionWrapper;

    socket.on('getHistory', () => {
        socket.emit('self:history', JSON.stringify(usernames));
    });

    socket.on('listenToUsername', data => {
        const { username, proxy } = JSON.parse(data);
        if (!username) return;

        if (proxy) console.log('Using proxy');

        try {
            if (tiktokConnectionWrapper) {
                tiktokConnectionWrapper.disconnect();
            }
            if (activeListenWrapper && activeListenWrapper !== tiktokConnectionWrapper) {
                try {
                    activeListenWrapper.disconnect();
                } catch (err) {
                    console.error('Failed to disconnect previous active listener', err);
                }
            }

            tiktokConnectionWrapper = new TikTokConnectionWrapper(username, createTorOptions(), true);
            activeListenWrapper = tiktokConnectionWrapper;
            setupConnectionEvents(tiktokConnectionWrapper, socket, username);
            tiktokConnectionWrapper.connect();
        } catch (err) {
            console.error(err);
        }
    });

    socket.on('disconnect', () => {
        console.log('Client disconnected');
        if (tiktokConnectionWrapper && activeListenWrapper === tiktokConnectionWrapper) {
            tiktokConnectionWrapper.disconnect();
            activeListenWrapper = null;
        }
    });

    socket.on('stopListen', () => {
        console.log('Client asking to stop');
        if (tiktokConnectionWrapper && activeListenWrapper === tiktokConnectionWrapper) {
            tiktokConnectionWrapper.disconnect();
            activeListenWrapper = null;
        }
        socket.emit('data-connection', JSON.stringify({ isConnected: false }));
    });
});

function setupConnectionEvents(wrapper, socket, username) {
    wrapper.on('connected', state => {
        if (!usernames.includes(username)) usernames.push(username);
        socket.emit('data-connection', JSON.stringify({ isConnected: true, state }));
    });

    wrapper.on('disconnected', reason => {
        const detail = reason && typeof reason === 'object'
            ? { ...reason }
            : { message: String(reason || 'Unknown error.'), rateLimited: false };
        let message = String(detail.message || 'Unknown error.');
        const reasonText = message;
        if (reasonText.includes('EAI_FAIL') || reasonText.includes('Unable to resolve') || reasonText.includes('Could not resolve')) {
            message = 'Falha de DNS/rede via Tor ao buscar a live no TikTok. Tor e obrigatorio; reinicie o Tor ou aguarde novo circuito.';
        } else if (reasonText.includes('Rate Limited') || reasonText.includes('SignatureRateLimitError') || reasonText.includes('rate_limit_')) {
            const retryAt = detail.retryAt
                ? new Date(detail.retryAt).toLocaleTimeString('pt-BR', {
                    hour: '2-digit',
                    minute: '2-digit',
                })
                : '';
            message = `Limite de conexoes TikTok/Euler atingido. Novas tentativas pausadas${retryAt ? ` ate ${retryAt}` : ''}.`;
        } else if (reasonText.includes('SignAPIError') || reasonText.includes('[Sign Error]') || reasonText.includes('Failed to sign request') || reasonText.includes('fetchSignedWebSocket')) {
            message = `Falha de assinatura TikTok/Euler no monitor via Tor: ${reasonText}`;
        } else if (reasonText.includes('status code 451')) {
            message = 'TikTok recusou a consulta da live com status 451. Normalmente e bloqueio/regiao/Tor ou live ainda indisponivel para monitoramento.';
        } else if (reasonText.includes('Failed to retrieve room_id from page source')) {
            message = 'Nao foi possivel obter o room_id da live. Verifique se a live ja esta aberta e se o usuario esta correto.';
        } else if (reasonText.includes('not offer a websocket upgrade.')) {
            message = 'Considering to use proxy or change server';
        }
        socket.emit('data-connection', JSON.stringify({
            isConnected: false,
            ...detail,
            message,
        }));
    });

    wrapper.connection.on('streamEnd', () => {
        if (activeListenWrapper === wrapper) {
            activeListenWrapper = null;
        }
        socket.emit(
            'data-connection',
            JSON.stringify({ isConnected: false, message: 'Stream ended. Reconnecting to current live room.' }),
        );
    });

    wrapper.on('roomInfo', roomInfo => socket.emit('data-roomInfo', roomInfo));
    wrapper.connection.on('liveIntro', data =>
        socket.emit('data-liveIntro', JSON.stringify({ data })),
    );
    wrapper.on('dataMessage', data => socket.emit('data-message', data));

    // Event mappings for TikTok connection
    wrapper.connection.on('chat', data => emitEvent(socket, 'data-chat', data));
    wrapper.connection.on('gift', data => emitEvent(socket, 'data-gift', data));
    wrapper.connection.on('member', data => socket.emit('data-member', JSON.stringify(data)));
    wrapper.connection.on('roomUser', data => socket.emit('data-viewer', JSON.stringify(data)));
    wrapper.connection.on('like', data => socket.emit('data-like', JSON.stringify(data)));
    wrapper.connection.on('social', data => {
        socket.emit('data-social', JSON.stringify(data));
        const displayType = String(data?.displayType || '').toLowerCase();
        const label = String(data?.label || '').toLowerCase();
        if (displayType.includes('share') || label.includes('shared') || label.includes('compartilhou')) {
            socket.emit('data-share', JSON.stringify(data));
        } else if (displayType.includes('follow') || label.includes('followed') || label.includes('seguiu')) {
            socket.emit('data-follow', JSON.stringify(data));
        }
    });
    wrapper.connection.on('share', data => socket.emit('data-share', JSON.stringify(data)));
    wrapper.connection.on('follow', data => socket.emit('data-follow', JSON.stringify(data)));
    wrapper.connection.on('linkMicBattle', data =>
        socket.emit('data-micBattle', JSON.stringify(data)),
    );
    wrapper.connection.on('linkMicArmies', data =>
        socket.emit('data-micArmies', JSON.stringify(data)),
    );
    wrapper.connection.on('subscribe', data => socket.emit('data-subscribe', JSON.stringify(data)));

    // TODO: Debug other events
    wrapper.connection.on('questionNew', data =>
        socket.emit('data-debug', JSON.stringify({ data, listener: 'questionNew' })),
    );
    wrapper.connection.on('emote', data =>
        socket.emit('data-debug', JSON.stringify({ data, listener: 'emote' })),
    );
    wrapper.connection.on('envelope', data =>
        socket.emit('data-debug', JSON.stringify({ data, listener: 'envelope' })),
    );
}

async function proxyStream(streamUrl, res) {
    const parsedUrl = new URL(streamUrl);
    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
        throw new Error('Protocolo de stream nao permitido.');
    }
    const response = await fetch(parsedUrl, { redirect: 'follow' });
    res.status(response.status);
    response.headers.forEach((value, name) => {
        if (!['connection', 'content-length', 'transfer-encoding'].includes(name.toLowerCase())) {
            res.setHeader(name, value);
        }
    });
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (!response.body) {
        res.end();
        return;
    }
    Readable.fromWeb(response.body).pipe(res);
}

app.get('/hist', (req, res) => {
    res.json(usernames);
});

app.get('/proxy-stream/:url/:segment', async (req, res) => {
    const { url, segment } = req.params;
    try {
        const query = req.query;
        let streamUrl = Buffer.from(reverseInPlace(url), 'base64').toString('utf-8');

        if (streamUrl.includes('index.m3u8')) {
            streamUrl = streamUrl.replace('index.m3u8', segment);
        } else if (streamUrl.includes('.m3u8')) {
            const parts = streamUrl.split('/');
            parts[parts.length - 1] = segment;
            streamUrl = parts.join('/');
        } else {
            console.error(`Unknown url`, { url }, { segment });
        }

        if (Object.keys(query).length > 0) {
            streamUrl += '?' + new URLSearchParams(query).toString();
        }

        await proxyStream(streamUrl, res);
    } catch (err) {
        console.error('Error fetching segment:', err);
        res.status(400).json({ message: 'Falha ao buscar o segmento.' });
    }
});

app.get('/proxy-stream/:url/', async (req, res) => {
    try {
        const { url } = req.params;
        const streamUrl = Buffer.from(reverseInPlace(url), 'base64').toString('utf-8');

        await proxyStream(streamUrl, res);
    } catch (err) {
        console.error('Error fetching segment:', err);
        res.status(400).json({ message: 'Falha ao buscar o segmento.' });
    }
});

app.post('/webhooks', async (req, res) => {
    res.json(req.body || {});
});

server.listen(PORT, HOST, () => {
    console.log(`Server is running on http://${HOST}:${PORT}`);
});
