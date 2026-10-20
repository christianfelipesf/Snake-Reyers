const $ = id => document.getElementById(id);

let latestSessionConfig = null;

function renderOpenAISettings(settings) {
  const model = $("openaiModel");
  const enabled = $("openaiEnabled");
  const status = $("openaiStatus");
  if (model && document.activeElement !== model) {
    model.value = settings?.model || "gpt-4.1-mini";
  }
  if (enabled) {
    enabled.checked = Boolean(settings?.enabled);
  }
  if (status) {
    status.textContent = settings?.api_key_present
      ? `Chave salva localmente · ${settings?.enabled ? "IA ativa" : "IA desativada"}`
      : "Nenhuma chave salva.";
  }
}

async function loadOpenAISettings() {
  const response = await fetch(
    "/api/settings/openai",
    { cache: "no-store" }
  );
  const payload = await response.json();
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  renderOpenAISettings(payload.settings || {});
  return payload.settings || {};
}

async function saveOpenAISettings(clearKey = false) {
  const key = $("openaiApiKey")?.value.trim() || "";
  const response = await fetch(
    "/api/settings/openai",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: clearKey ? "" : key,
        clear_key: clearKey,
        enabled: clearKey ? false : Boolean($("openaiEnabled")?.checked),
        model: $("openaiModel")?.value.trim() || "gpt-4.1-mini"
      })
    }
  );
  const payload = await response.json();
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  if ($("openaiApiKey")) {
    $("openaiApiKey").value = "";
  }
  renderOpenAISettings(payload.settings || {});
  return payload.settings || {};
}

function setState(id, text, active) {
  const node = $(id);
  node.textContent = text;
  node.className = `value ${active ? "ok" : "off"}`;
}

function renderLiveHealth(watchdog) {
  const status =
    String(watchdog?.status || "idle").toLowerCase();
  const labels = {
    ok: "OK",
    warning: "ALERTA",
    critical: "CRÍTICO",
    idle: "OCIOSO"
  };
  const active =
    status === "ok";

  setState(
    "liveHealth",
    labels[status] || status.toUpperCase(),
    active
  );

  const detail = $("liveHealthDetail");
  if (!detail) return;

  const issues = Array.isArray(watchdog?.issues)
    ? watchdog.issues
    : [];

  if (!issues.length) {
    detail.textContent =
      status === "idle"
        ? "Sem jogo aberto."
        : "Sem alertas.";
    return;
  }

  const first = issues[0] || {};
  detail.textContent =
    first.message
    || first.code
    || "Verificar diagnóstico.";
}

function sessionConfigFromForm() {
  return {
    username:
      ($("sessionUsername")?.value.trim() || "")
        .replace(/^@+/, ""),
    monitor_server:
      $("sessionMonitorServer")?.value.trim()
      || "http://127.0.0.1:2619",
    game_runtime:
      $("sessionGameRuntime")?.value
      || "build",
    godot_executable:
      $("sessionGodotExecutable")?.value.trim()
      || "",
    display:
      $("sessionDisplay")?.value.trim()
      || ""
  };
}

function applySessionConfig(config) {
  if (!config) return;

  if (
    $("sessionUsername")
    && document.activeElement !== $("sessionUsername")
  ) {
    $("sessionUsername").value =
      config.username || "";
  }

  if (
    $("sessionMonitorServer")
    && document.activeElement !== $("sessionMonitorServer")
  ) {
    $("sessionMonitorServer").value =
      config.monitor_server || "http://127.0.0.1:2619";
  }

  if ($("sessionGameRuntime")) {
    $("sessionGameRuntime").value =
      config.game_runtime || "build";
  }

  if (
    $("sessionGodotExecutable")
    && document.activeElement !== $("sessionGodotExecutable")
  ) {
    $("sessionGodotExecutable").value =
      config.godot_executable || "";
  }

  if (
    $("sessionDisplay")
    && document.activeElement !== $("sessionDisplay")
  ) {
    $("sessionDisplay").value =
      config.display || "";
  }

  if (
    $("monitorUsername")
    && document.activeElement !== $("monitorUsername")
  ) {
    $("monitorUsername").value =
      config.username || "";
  }
}

function sessionIsActuallyRunning(payload) {
  const session = payload?.session || {};
  return Boolean(
    session.running
    || ["starting", "running", "stopping"].includes(
      String(session.state || "").toLowerCase()
    )
  );
}

async function loadSessionConfig() {
  const response = await fetch(
    "/api/session/config",
    { cache: "no-store" }
  );

  const payload = await response.json();

  if (!response.ok || payload?.ok === false) {
    throw new Error(
      payload?.error
      || `HTTP ${response.status}`
    );
  }

  latestSessionConfig =
    payload.config || {};

  applySessionConfig(
    latestSessionConfig
  );

  return latestSessionConfig;
}

async function saveSessionConfig() {
  const config =
    sessionConfigFromForm();

  const response = await fetch(
    "/api/session/config",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(config)
    }
  );

  const payload = await response.json();

  if (!response.ok || payload?.ok === false) {
    throw new Error(
      payload?.error
      || `HTTP ${response.status}`
    );
  }

  latestSessionConfig =
    payload.config || config;

  applySessionConfig(
    latestSessionConfig
  );

  return latestSessionConfig;
}

function openTextureModal() {
  const modal = $("textureModal");
  if (!modal) return;

  if (typeof modal.showModal === "function") {
    modal.showModal();
  } else {
    modal.setAttribute("open", "open");
  }

  refreshTextureLibrary().catch(
    error => {
      const target = $("textureStatus");
      if (target) {
        target.textContent = String(error);
      }
    }
  );
}

function closeTextureModal() {
  const modal = $("textureModal");
  if (!modal) return;

  if (typeof modal.close === "function") {
    modal.close();
  } else {
    modal.removeAttribute("open");
  }
}

function closeSystemUpdateModal() {
  const modal = $("systemUpdateModal");
  if (!modal) return;

  if (typeof modal.close === "function") {
    modal.close();
  } else {
    modal.removeAttribute("open");
  }
}

function renderSystemUpdate(payload) {
  const top = $("systemUpdateTop");
  const badge = $("systemUpdateBadge");
  const title = $("systemUpdateTitle");
  const versions = $("systemUpdateVersions");
  const notice = $("systemUpdateLiveNotice");
  const output = $("systemUpdateOutput");
  const checkButton = $("systemUpdateCheck");
  const installButton = $("systemUpdateInstall");
  const busy = Boolean(payload?.busy);
  const restarting = Boolean(payload?.restart_scheduled);
  const available = Boolean(payload?.update_available);
  const gameActive = Boolean(payload?.live_active);
  const current = payload?.current || "desconhecida";
  const next = payload?.available || "não consultada";

  top?.classList.toggle("update-available", available);
  if (top) {
    top.textContent = restarting
      ? "Reiniciando..."
      : available
        ? `Atualizar para ${next}`
        : "Atualizar sistema";
    top.disabled = restarting;
  }
  if (badge) {
    badge.textContent = restarting
      ? "Reiniciando"
      : busy
      ? "Processando"
      : available
        ? "Disponível"
        : payload?.checked_at
          ? "Atualizado"
          : "Aguardando";
  }
  if (title) {
    title.textContent = available
      ? `Nova versão ${next} disponível`
      : "Sistema atualizado";
  }
  if (versions) {
    versions.textContent = `Instalada: ${current} · Disponível: ${next}`;
  }
  if (notice) {
    notice.textContent = gameActive
      ? "O jogo está aberto. Feche-o antes de instalar."
      : "A instalação preserva configurações, músicas e dados locais.";
  }
  if (output) {
    output.textContent = payload?.error
      || payload?.last_error
      || payload?.message
      || "Atualização ainda não consultada.";
  }
  if (checkButton) {
    checkButton.disabled = busy;
    checkButton.textContent = busy ? "Verificando..." : "Verificar novamente";
  }
  if (installButton) {
    installButton.disabled = busy || restarting || !available || gameActive;
    installButton.textContent = restarting
      ? "Reiniciando..."
      : busy
      ? "Atualizando..."
      : "Baixar, instalar e reiniciar";
  }
}

async function loadSystemUpdateStatus() {
  const response = await fetch("/api/system-updates", { cache: "no-store" });
  const payload = await response.json();
  renderSystemUpdate(payload);
  return payload;
}

async function runSystemUpdate(action) {
  const response = await fetch(`/api/system-updates/${action}`, { method: "POST" });
  const payload = await response.json();
  renderSystemUpdate(payload);
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function waitForSystemRestart() {
  const output = $("systemUpdateOutput");
  const deadline = Date.now() + 120000;
  let observedOffline = false;

  while (Date.now() < deadline) {
    await new Promise(resolve => window.setTimeout(resolve, 1000));
    try {
      const response = await fetch("/api/health", { cache: "no-store" });
      if (response.ok && observedOffline) {
        window.location.reload();
        return;
      }
    } catch (error) {
      observedOffline = true;
      if (output) output.textContent = "Sistema reiniciando. Aguarde...";
    }
  }

  if (output) {
    output.textContent = "O reinício demorou mais que o esperado. Abra o painel novamente.";
  }
}

async function openSystemUpdateModal() {
  const modal = $("systemUpdateModal");
  if (!modal) return;

  if (typeof modal.showModal === "function") {
    modal.showModal();
  } else {
    modal.setAttribute("open", "open");
  }

  await runSystemUpdate("check");
}

function renderTextureStatus(payload) {
  const target = $("textureStatus");
  if (!target) return;

  const counts =
    payload?.counts || {};
  const textures =
    payload?.manifest?.textures || [];

  const summary = [
    `Manifesto: ${payload?.manifest_path || ""}`,
    `Pasta: ${payload?.library_dir || ""}`,
    "",
    `piso: ${counts.piso || 0}`,
    `parede: ${counts.parede || 0}`,
    `grama: ${counts.grama || 0}`,
    `elevacao: ${counts.elevacao || 0}`,
    "",
    "Texturas:",
    ...textures.slice(-12).map(
      item => (
        `${item.type} · ${item.label || item.id} · ${item.path}`
      )
    )
  ];

  target.textContent =
    summary.join("\n");
}

async function refreshTextureLibrary() {
  const response = await fetch(
    "/api/textures"
  );
  const payload =
    await response.json();

  renderTextureStatus(payload);

  if (
    !response.ok
    || payload?.ok === false
  ) {
    throw new Error(
      payload?.error
      || `HTTP ${response.status}`
    );
  }

  return payload;
}

async function uploadTexture() {
  const fileInput = $("textureFile");
  const file = fileInput?.files?.[0];

  if (!file) {
    throw new Error(
      "Selecione um arquivo PNG, JPG ou WEBP."
    );
  }

  const form = new FormData();
  form.append(
    "texture_type",
    $("textureType")?.value || "piso"
  );
  form.append(
    "label",
    $("textureLabel")?.value.trim() || file.name
  );
  form.append(
    "file",
    file
  );

  const response = await fetch(
    "/api/textures/upload",
    {
      method: "POST",
      body: form
    }
  );
  const payload =
    await response.json();

  renderTextureStatus(payload);

  if (
    !response.ok
    || payload?.ok === false
  ) {
    throw new Error(
      payload?.error
      || `HTTP ${response.status}`
    );
  }

  if (fileInput) {
    fileInput.value = "";
  }

  return payload;
}

function formatBuildStatus(payload) {
  if (!payload) {
    return "Build ainda não consultado.";
  }

  return JSON.stringify(
    {
      estado: payload.state,
      rodando: payload.running,
      mensagem: payload.message || "",
      executavel: payload.executable,
      executavel_existe:
        payload.executable_exists,
      pck_existe:
        payload.pck_exists,
      templates_prontos:
        payload.templates_ready,
      pasta_templates:
        payload.templates_dir,
      usado_para_live:
        payload.used_for_live || false,
      log: payload.log_file,
      erro: payload.last_error || ""
    },
    null,
    2
  );
}

async function refreshBuildStatus() {
  const result = $("buildResult");
  const buildButton = $("buildGodot");
  const topButton = $("buildGodotTop");

  if (!result) {
    return null;
  }

  const response = await fetch(
    "/api/build/status",
    { cache: "no-store" }
  );

  const payload = await response.json();

  result.textContent =
    formatBuildStatus(payload);

  const running =
    Boolean(payload.running);

  if (buildButton) {
    buildButton.disabled = running;
    buildButton.textContent =
      running
        ? "Compilando..."
        : "Compilar nova versão";
  }

  if (topButton) {
    topButton.disabled = running;
    topButton.textContent =
      running
        ? "Compilando..."
        : "Compilar release";
  }

  return payload;
}

async function startGodotBuild() {
  const result = $("buildResult");
  const buildButton = $("buildGodot");
  const topButton = $("buildGodotTop");

  if (buildButton) {
    buildButton.disabled = true;
  }

  if (topButton) {
    topButton.disabled = true;
  }

  const response = await fetch(
    "/api/build/godot",
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json"
      },
      body: JSON.stringify({
        use_for_live:
          $("buildUseForLive")?.checked
          !== false
      })
    }
  );

  const payload = await response.json();

  if (result) {
    result.textContent =
      formatBuildStatus(payload);
  }

  if (!response.ok || payload?.ok === false) {
    throw new Error(
      payload?.error
      || payload?.last_error
      || `HTTP ${response.status}`
    );
  }

  setTimeout(
    () => refreshBuildStatus().catch(console.error),
    1200
  );

  return payload;
}

async function refresh() {
  const response = await fetch(
    "/api/status",
    { cache: "no-store" }
  );
  const state = await response.json();

  let monitorState = {
    ok: false,
    monitor: {},
    events: {},
    social_dispatcher: {}
  };

  try {
    const monitorResponse = await fetch(
      "/api/monitor/status",
      { cache: "no-store" }
    );

    monitorState =
      await monitorResponse.json();
  } catch (error) {
    monitorState = {
      ok: false,
      error: String(error),
      monitor: {},
      events: {},
      social_dispatcher: {}
    };
  }

  setState(
    "server",
    state.ok ? "ATIVO" : "ERRO",
    Boolean(state.ok)
  );

  setState(
    "godot",
    state.godot?.connected
      ? "CONECTADO"
      : "DESCONECTADO",
    Boolean(state.godot?.connected)
  );

  setState(
    "game",
    state.game?.running
      ? "ABERTO"
      : "FECHADO",
    Boolean(state.game?.running)
  );

  setState(
    "vocal",
    String(
      state.vocal?.mode || "idle"
    ).toUpperCase(),
    Boolean(state.vocal?.active)
  );

  renderLiveHealth(
    state.watchdog || {}
  );

  const voiceReady = Object.values(
    state.voice_stack || {}
  ).every(Boolean);

  setState(
    "voice",
    voiceReady
      ? "INSTALADO"
      : "PENDENTE",
    voiceReady
  );

  const background =
    Number(
      state.music?.background_tracks || 0
    );

  const musicRuntime =
    state.music?.runtime || {};

  setState(
    "music",
    `${background} faixa(s) de fundo`,
    background > 0
  );

  const musicVolume = $("musicVolume");
  const musicVolumeValue = $("musicVolumeValue");
  const musicEnabled = $("musicEnabled");
  const musicRuntimeStatus = $("musicRuntimeStatus");

  if (
    musicVolume
    && document.activeElement !== musicVolume
  ) {
    musicVolume.value = String(
      Math.round(
        Number(
          musicRuntime.volume ?? 0.16
        ) * 100
      )
    );
  }

  if (musicVolumeValue) {
    musicVolumeValue.textContent =
      `${Math.round(
        Number(
          musicVolume?.value
          || Number(
            musicRuntime.volume ?? 0.16
          ) * 100
        )
      )}%`;
  }

  if (
    musicEnabled
    && document.activeElement !== musicEnabled
  ) {
    musicEnabled.checked =
      musicRuntime.enabled !== false;
  }

  if (musicRuntimeStatus) {
    const trackCount = Number(
      musicRuntime.track_count
      || musicRuntime.tracks?.length
      || 0
    );

    musicRuntimeStatus.textContent =
      `${musicRuntime.enabled !== false ? "Ligada" : "Desligada"} · `
      + `${trackCount} faixa(s) · `
      + `${Math.round(
          Number(
            musicRuntime.volume ?? 0.16
          ) * 100
        )}%`;
  }

  const monitorRunning = Boolean(
    monitorState.monitor?.running
  );

  const monitorListening = Boolean(
    monitorState.monitor?.listening
  );

  const monitorError = String(
    monitorState.monitor?.last_error || ""
  );

  const liveNotFound = (
    !monitorListening
    && /live nao encontrada|failed to retrieve room id/i
      .test(monitorError)
  );

  const monitorRateLimited = Boolean(
    monitorState.monitor?.rate_limited
  );

  setState(
    "monitor",
    monitorRateLimited
      ? "LIMITE TEMPORÁRIO · AGUARDANDO"
      : liveNotFound
      ? "LIVE NÃO ENCONTRADA"
      : monitorListening
      ? "ESCUTANDO LIVE"
      : (
          monitorRunning
            ? "CONECTANDO"
            : "PARADO"
        ),
    monitorListening
  );

  const monitorResult = $("monitorResult");
  if (
    monitorResult
    && (liveNotFound || monitorRateLimited)
  ) {
    monitorResult.textContent = monitorError;
  }

  const commentsPending = Number(
    monitorState.events
      ?.comments_pending || 0
  );

  const giftsPending = Number(
    monitorState.events
      ?.gifts_pending || 0
  );

  const giftsReceived = Number(
    monitorState.monitor
      ?.counters?.gift || 0
  );

  const giftsAtSocket = Number(
    monitorState.monitor
      ?.counters?.gift_socket || 0
  );

  setState(
    "socialEvents",
    `${commentsPending} comentários / ${giftsPending} presentes na fila | `
      + `${giftsReceived}/${giftsAtSocket} presentes aceitos`,
    commentsPending > 0
      || giftsPending > 0
      || giftsReceived > 0
  );

  $("monitorStart").disabled =
    monitorRunning;

  $("monitorStop").disabled =
    !monitorRunning;

  $("testEvent").disabled =
    !state.godot?.connected;

  $("speechSend").disabled =
    !state.godot?.connected;

  $("state").textContent =
    JSON.stringify(
      state,
      null,
      2
    );

  refreshBuildStatus().catch(
    () => {}
  );
}

async function previewSpeech() {
  const text = $("speechText").value;

  const response = await fetch(
    "/api/speech/prepare-text",
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json"
      },
      body: JSON.stringify({
        text
      })
    }
  );

  const payload =
    await response.json();

  $("preparedText").textContent =
    payload.prepared
    || payload.error
    || "(vazio)";

  $("speechResult").textContent =
    JSON.stringify(
      payload,
      null,
      2
    );

  return payload;
}

async function sendSpeechTest() {
  const text = $("speechText").value;

  const preview =
    await previewSpeech();

  if (!preview.ok) {
    return;
  }

  const response = await fetch(
    "/api/speech/manual",
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json"
      },
      body: JSON.stringify({
        text
      })
    }
  );

  const payload =
    await response.json();

  $("speechResult").textContent =
    JSON.stringify(
      payload,
      null,
      2
    );

  if (!response.ok || payload?.ok === false) {
    throw new Error(
      payload?.error
      || `HTTP ${response.status}`
    );
  }

  setTimeout(
    refresh,
    400
  );
}

async function startMonitor() {
  const config =
    sessionConfigFromForm();

  const username =
    (
      $("monitorUsername").value.trim()
      || config.username
    ).replace(/^@+/, "");

  if (!username) {
    $("monitorResult").textContent =
      "Informe o usuário TikTok antes de conectar.";
    return;
  }

  $("monitorStart").disabled = true;

  try {
    const response = await fetch(
      "/api/monitor/start",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body: JSON.stringify({
          username,
          server_url:
            config.monitor_server,
          prepare_local_node: true
        })
      }
    );

    const payload =
      await response.json();

    $("monitorResult").textContent =
      JSON.stringify(
        payload,
        null,
        2
      );
  } finally {
    await refresh();
  }
}

async function stopMonitor() {
  $("monitorStop").disabled = true;

  try {
    const response = await fetch(
      "/api/monitor/stop",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body: JSON.stringify({
          stop_local_node_runtime: true
        })
      }
    );

    const payload =
      await response.json();

    $("monitorResult").textContent =
      JSON.stringify(
        payload,
        null,
        2
      );
  } finally {
    await refresh();
  }
}

let musicRuntimeUpdateTimer = 0;

async function updateMusicRuntime() {
  const volumeNode = $("musicVolume");
  const enabledNode = $("musicEnabled");

  if (!volumeNode || !enabledNode) {
    return;
  }

  const volume = Math.max(
    0,
    Math.min(
      1,
      Number(volumeNode.value || 0) / 100
    )
  );

  $("musicVolumeValue").textContent =
    `${Math.round(volume * 100)}%`;

  const response = await fetch(
    "/api/music/runtime",
    {
      method: "POST",
      headers: {
        "Content-Type":
          "application/json"
      },
      body: JSON.stringify({
        volume,
        enabled:
          Boolean(enabledNode.checked)
      })
    }
  );

  const payload =
    await response.json();

  if (
    !response.ok
    || payload?.ok === false
  ) {
    throw new Error(
      payload?.error
      || `HTTP ${response.status}`
    );
  }

  const runtime = payload.music || {};
  const trackCount = Number(
    runtime.track_count
    || runtime.tracks?.length
    || 0
  );

  $("musicRuntimeStatus").textContent =
    `${runtime.enabled !== false ? "Ligada" : "Desligada"} · `
    + `${trackCount} faixa(s) · `
    + `${Math.round(
        Number(runtime.volume || 0) * 100
      )}%`;
}

function queueMusicRuntimeUpdate() {
  clearTimeout(
    musicRuntimeUpdateTimer
  );

  musicRuntimeUpdateTimer =
    setTimeout(
      () => {
        updateMusicRuntime()
          .catch(error => {
            const node =
              $("musicRuntimeStatus");

            if (node) {
              node.textContent =
                String(error);
            }
          });
      },
      80
    );
}

$("musicVolume")?.addEventListener(
  "input",
  () => {
    const node =
      $("musicVolumeValue");

    if (node) {
      node.textContent =
        `${$("musicVolume").value}%`;
    }

    queueMusicRuntimeUpdate();
  }
);

$("musicEnabled")?.addEventListener(
  "change",
  queueMusicRuntimeUpdate
);

$("buildGodot")?.addEventListener(
  "click",
  () => {
    startGodotBuild().catch(
      error => {
        const result =
          $("buildResult");

        if (result) {
          result.textContent =
            String(error);
        }
      }
    );
  }
);

$("buildGodotTop")?.addEventListener(
  "click",
  () => {
    startGodotBuild().catch(
      error => {
        const result =
          $("buildResult")
          || $("sessionResult");

        if (result) {
          result.textContent =
            String(error);
        }
      }
    );
  }
);

function formatCleanupBytes(value) {
  let bytes = Number(value || 0);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unit = 0;

  while (bytes >= 1024 && unit < units.length - 1) {
    bytes /= 1024;
    unit += 1;
  }

  return `${bytes.toFixed(unit === 0 ? 0 : 2)} ${units[unit]}`;
}

function renderContentUpdates(payload) {
  const badge = $("contentUpdateBadge");
  const result = $("contentUpdateResult");
  const checkButton = $("contentCheck");
  const installButton = $("contentInstall");
  const autoInstall = $("contentAutoInstall");
  const available = Number(payload?.available_count || 0);
  const busy = Boolean(payload?.busy);
  const hasError = Boolean(payload?.last_error);

  if ($("contentInstalledCount")) {
    $("contentInstalledCount").textContent = String(payload?.installed_count || 0);
  }
  if ($("contentAvailableCount")) {
    $("contentAvailableCount").textContent = String(available);
  }
  if ($("contentDownloadSize")) {
    $("contentDownloadSize").textContent = formatCleanupBytes(payload?.download_bytes);
  }
  if (autoInstall && document.activeElement !== autoInstall) {
    autoInstall.checked = Boolean(payload?.configuration?.auto_install);
  }
  if (checkButton) {
    checkButton.disabled = busy;
    checkButton.textContent = busy ? "Verificando..." : "Procurar novidades";
  }
  if (installButton) {
    installButton.disabled = busy || available < 1 || Boolean(payload?.live_active);
    installButton.textContent = busy ? "Processando..." : "Baixar e instalar";
  }
  if (badge) {
    badge.className = "content-update-badge";
    if (hasError) {
      badge.textContent = "Atenção";
      badge.classList.add("has-error");
    } else if (busy) {
      badge.textContent = "Processando";
    } else if (available > 0) {
      badge.textContent = `${available} novidade${available === 1 ? "" : "s"}`;
      badge.classList.add("has-updates");
    } else {
      badge.textContent = payload?.checked_at ? "Atualizado" : "Aguardando";
    }
  }
  if (result) {
    const lines = [payload?.message || "Catálogo ainda não consultado."];
    const items = Array.isArray(payload?.available) ? payload.available : [];
    items.forEach(item => {
      lines.push(`- ${item.title || item.id} · versão ${item.version} · ${formatCleanupBytes(item.bytes)}`);
    });
    if (payload?.live_active && available > 0) {
      lines.push("A instalação aguardará o jogo fechar.");
    }
    result.textContent = lines.join("\n");
  }
}

async function loadContentUpdates() {
  const response = await fetch("/api/content-updates", { cache: "no-store" });
  const payload = await response.json();
  renderContentUpdates(payload);
  return payload;
}

async function runContentUpdate(action) {
  const response = await fetch(`/api/content-updates/${action}`, { method: "POST" });
  const payload = await response.json();
  renderContentUpdates(payload);
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function saveContentUpdateSettings() {
  const response = await fetch(
    "/api/content-updates/settings",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        auto_install: Boolean($("contentAutoInstall")?.checked)
      })
    }
  );
  const payload = await response.json();
  renderContentUpdates(payload);
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload;
}

function renderCleanupResult(payload) {
  const target = $("cleanupResult");
  if (!target) return;

  const categories = payload?.categories || {};
  const lines = [
    payload?.mode === "cleanup"
      ? "Limpeza concluída."
      : "Análise concluída.",
    `Itens: ${Number(payload?.items || 0)}`,
    `Espaço: ${formatCleanupBytes(payload?.bytes)}`,
    `Protegidos em uso: ${Number(payload?.protected_files || 0)}`
  ];

  const automatic = payload?.automatic_cleanup;
  if (automatic && typeof automatic === "object") {
    const completed = Number(automatic.completed_lives || 0);
    const interval = Number(automatic.cleanup_every_lives || 3);
    lines.push(`Ciclo automático: ${completed}/${interval} lives concluídas`);
  }

  Object.entries(categories).forEach(([name, item]) => {
    lines.push(
      `${name}: ${Number(item?.items || 0)} itens, ${formatCleanupBytes(item?.bytes)}`
    );
  });

  if (payload?.error) {
    lines.push(`Erro: ${payload.error}`);
  }
  if (payload?.blocked_reason) {
    lines.push(`Bloqueado: ${payload.blocked_reason}`);
  }
  if (Number(payload?.error_count || 0) > 0) {
    lines.push(`Falhas: ${payload.error_count}`);
  }

  target.textContent = lines.join("\n");
}

async function analyzeCleanup() {
  const response = await fetch(
    "/api/maintenance/cleanup",
    { cache: "no-store" }
  );
  const payload = await response.json();
  renderCleanupResult(payload);
  if (!response.ok || payload?.ok === false) {
    throw new Error(payload?.error || `HTTP ${response.status}`);
  }
  return payload;
}

async function runCleanup() {
  const button = $("cleanupRun");
  if (button) {
    button.disabled = true;
    button.textContent = "Limpando...";
  }

  try {
    const response = await fetch(
      "/api/maintenance/cleanup",
      { method: "POST" }
    );
    const payload = await response.json();
    renderCleanupResult(payload);
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.error || `HTTP ${response.status}`);
    }
    return payload;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Limpar temporários agora";
    }
  }
}

$("cleanupAnalyze")?.addEventListener(
  "click",
  () => {
    analyzeCleanup().catch(error => {
      const target = $("cleanupResult");
      if (target) target.textContent = String(error);
    });
  }
);

$("cleanupRun")?.addEventListener(
  "click",
  () => {
    runCleanup().catch(error => {
      const target = $("cleanupResult");
      if (target) target.textContent = String(error);
    });
  }
);

$("contentCheck")?.addEventListener(
  "click",
  () => {
    runContentUpdate("check").catch(error => {
      const target = $("contentUpdateResult");
      if (target) target.textContent = String(error);
    });
  }
);

$("contentInstall")?.addEventListener(
  "click",
  () => {
    runContentUpdate("install").catch(error => {
      const target = $("contentUpdateResult");
      if (target) target.textContent = String(error);
    });
  }
);

$("contentAutoInstall")?.addEventListener(
  "change",
  () => {
    saveContentUpdateSettings().catch(error => {
      const target = $("contentUpdateResult");
      if (target) target.textContent = String(error);
    });
  }
);

$("monitorStart").addEventListener(
  "click",
  () => {
    startMonitor().catch(
      error => {
        $("monitorResult").textContent =
          String(error);
      }
    );
  }
);

$("monitorStop").addEventListener(
  "click",
  () => {
    stopMonitor().catch(
      error => {
        $("monitorResult").textContent =
          String(error);
      }
    );
  }
);

$("speechPreview").addEventListener(
  "click",
  () => {
    previewSpeech().catch(
      error => {
        $("speechResult").textContent =
          String(error);
      }
    );
  }
);

$("speechSend").addEventListener(
  "click",
  () => {
    sendSpeechTest().catch(
      error => {
        $("speechResult").textContent =
          String(error);
      }
    );
  }
);

$("refresh").addEventListener(
  "click",
  () => {
    Promise.all([
      refresh(),
      loadSessionConfig()
    ]).catch(console.error);
  }
);

$("sessionSave")?.addEventListener(
  "click",
  () => {
    saveSessionConfig().catch(error => {
      const result = $("sessionResult");
      if (result) result.textContent = String(error);
    });
  }
);

$("testEvent").addEventListener(
  "click",
  async () => {
    const response = await fetch(
      "/api/godot/test-event",
      {
        method: "POST",
        headers: {
          "Content-Type":
            "application/json"
        },
        body: JSON.stringify({
          type: "integration_test",
          payload: {
            message:
              "teste do painel"
          }
        })
      }
    );

    const payload =
      await response.json();

    $("state").textContent =
      JSON.stringify(
        payload,
        null,
        2
      );

    setTimeout(
      refresh,
      500
    );
  }
);

refresh().catch(console.error);
setInterval(
  () => refresh().catch(console.error),
  1500
);
setInterval(
  () => refreshSessionControl().catch(console.error),
  3000
);

async function refreshSessionControl() {
  const response = await fetch(
    "/api/session/status",
    { cache: "no-store" }
  );

  const payload = await response.json();

  const running =
    sessionIsActuallyRunning(payload);

  const top =
    $("liveToggleTop");

  if (top) {
    top.textContent =
      running
        ? "Fechar jogo"
        : "Abrir jogo";

    top.classList.toggle(
      "running",
      running
    );
  }

  const startButton =
    $("sessionStart");

  const stopButton =
    $("sessionStop");

  if (startButton) {
    startButton.disabled =
      running;
  }

  if (stopButton) {
    stopButton.disabled =
      !running;
  }

  const config =
    payload.config || {};

  if (!latestSessionConfig) {
    latestSessionConfig = config;
    applySessionConfig(config);
  }

  return payload;
}

async function requestSessionStart() {
  const config =
    await saveSessionConfig();

  const response = await fetch(
    "/api/session/start",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(config)
    }
  );

  const payload = await response.json();

  const result = $("sessionResult");

  if (result) {
    result.textContent =
      JSON.stringify(payload, null, 2);
  }

  await refreshSessionControl();

  return payload;
}

async function requestSessionStop() {
  const response = await fetch(
    "/api/session/stop",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({})
    }
  );

  const payload = await response.json();

  const result = $("sessionResult");

  if (result) {
    result.textContent =
      JSON.stringify(payload, null, 2);
  }

  await refreshSessionControl();

  return payload;
}

$("openaiSave")?.addEventListener(
  "click",
  () => {
    saveOpenAISettings(false).catch(error => {
      if ($("openaiStatus")) $("openaiStatus").textContent = String(error);
    });
  }
);

$("openaiRemove")?.addEventListener(
  "click",
  () => {
    saveOpenAISettings(true).catch(error => {
      if ($("openaiStatus")) $("openaiStatus").textContent = String(error);
    });
  }
);

$("openTextureModal")?.addEventListener(
  "click",
  openTextureModal
);

$("closeTextureModal")?.addEventListener(
  "click",
  closeTextureModal
);

$("systemUpdateTop")?.addEventListener(
  "click",
  () => {
    openSystemUpdateModal().catch(error => {
      const output = $("systemUpdateOutput");
      if (output) output.textContent = String(error);
    });
  }
);

$("closeSystemUpdateModal")?.addEventListener(
  "click",
  closeSystemUpdateModal
);

$("systemUpdateCheck")?.addEventListener(
  "click",
  () => {
    runSystemUpdate("check").catch(error => {
      const output = $("systemUpdateOutput");
      if (output) output.textContent = String(error);
    });
  }
);

$("systemUpdateInstall")?.addEventListener(
  "click",
  () => {
    runSystemUpdate("install")
      .then(payload => {
        if (payload?.restart_scheduled) {
          waitForSystemRestart();
        }
      })
      .catch(error => {
        const output = $("systemUpdateOutput");
        if (output) output.textContent = String(error);
      });
  }
);

$("refreshTextures")?.addEventListener(
  "click",
  () => {
    refreshTextureLibrary().catch(
      error => {
        const target = $("textureStatus");
        if (target) {
          target.textContent =
            String(error);
        }
      }
    );
  }
);

$("uploadTexture")?.addEventListener(
  "click",
  () => {
    const button = $("uploadTexture");
    if (button) {
      button.disabled = true;
    }

    uploadTexture()
      .catch(
        error => {
          const target = $("textureStatus");
          if (target) {
            target.textContent =
              String(error);
          }
        }
      )
      .finally(
        () => {
          if (button) {
            button.disabled = false;
          }
        }
      );
  }
);

$("sessionStart")?.addEventListener(
  "click",
  () => {
    requestSessionStart().catch(
      error => {
        const result =
          $("sessionResult");

        if (result) {
          result.textContent =
            String(error);
        }
      }
    );
  }
);

$("sessionStop")?.addEventListener(
  "click",
  () => {
    requestSessionStop().catch(
      error => {
        const result =
          $("sessionResult");

        if (result) {
          result.textContent =
            String(error);
        }
      }
    );
  }
);

$("liveToggleTop")?.addEventListener(
  "click",
  async () => {
    try {
      const payload =
        await refreshSessionControl();

      const state =
        sessionIsActuallyRunning(payload);

      if (state) {
        await requestSessionStop();
      } else {
        await requestSessionStart();
      }
    } catch (error) {
      const result =
        $("sessionResult");

      if (result) {
        result.textContent =
          String(error);
      }
    }
  }
);

refreshSessionControl().catch(
  error => {
    const result =
      $("sessionResult");

    if (result) {
      result.textContent =
        String(error);
    }
  }
);

loadSessionConfig().catch(
  error => {
    const result =
      $("sessionResult");

    if (result) {
      result.textContent =
        String(error);
    }
  }
);

loadOpenAISettings().catch(
  error => {
    if ($("openaiStatus")) {
      $("openaiStatus").textContent = String(error);
    }
  }
);

refreshBuildStatus().catch(
  error => {
    const result =
      $("buildResult");

    if (result) {
      result.textContent =
        String(error);
    }
  }
);

loadContentUpdates().catch(
  error => {
    const result = $("contentUpdateResult");
    if (result) result.textContent = String(error);
  }
);

loadSystemUpdateStatus().catch(
  error => {
    const output = $("systemUpdateOutput");
    if (output) output.textContent = String(error);
  }
);

async function copyPixKey() {
  const key = $("pixKey")?.textContent?.trim();
  const button = $("copyPix");
  const status = $("pixCopyStatus");

  if (!key || !button || !status) {
    return;
  }

  const originalLabel = button.textContent;

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(key);
    } else {
      const temporaryInput = document.createElement("textarea");
      temporaryInput.value = key;
      temporaryInput.setAttribute("readonly", "");
      temporaryInput.style.position = "fixed";
      temporaryInput.style.opacity = "0";
      document.body.appendChild(temporaryInput);
      temporaryInput.select();

      if (!document.execCommand("copy")) {
        throw new Error("Nao foi possivel copiar a chave Pix.");
      }

      temporaryInput.remove();
    }

    button.textContent = "Copiado";
    status.textContent = "Chave Pix copiada.";
  } catch (error) {
    status.textContent = "Nao foi possivel copiar. Selecione a chave acima.";
  } finally {
    window.setTimeout(() => {
      button.textContent = originalLabel;
      status.textContent = "";
    }, 3000);
  }
}

$("copyPix")?.addEventListener("click", copyPixKey);
