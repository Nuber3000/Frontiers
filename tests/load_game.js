import http from 'k6/http';
import { sleep } from 'k6';
import { WebSocket } from 'k6/websockets';
import { Counter, Trend } from 'k6/metrics';
import execution from 'k6/execution';

// One VU owns one room and two independent authenticated players.
function integer(name, fallback, min, max) {
  const value = Number(__ENV[name] ?? fallback);
  if (!Number.isInteger(value) || value < min || value > max)
    throw new Error(`${name} must be an integer between ${min} and ${max}`);
  return value;
}
const BASE = (__ENV.BASE_URL || '').replace(/\/+$/, '');
if (!/^https?:\/\/[^\s/?#@]+$/.test(BASE)) throw new Error('Set BASE_URL to the exact game origin, e.g. http://127.0.0.1:8000');
const ROOMS = integer('ROOMS', 5, 1, 128);
const SECONDS = integer('SECONDS', 60, 5, 900);
const THINK_MS = integer('THINK_MS', 2000, 250, 60000);
const RAMP_SECONDS = integer('RAMP_SECONDS', 5, 0, 300);
const TIMEOUT_MS = 5000;
const commands = new Counter('frontiers_commands');
const errors = new Counter('frontiers_errors');
const healthErrors = new Counter('frontiers_health_errors');
const matches = new Counter('frontiers_matches');
const rooms = new Counter('frontiers_rooms');
const connectedRooms = new Counter('frontiers_connected_rooms');
const capacityRejections = new Counter('frontiers_capacity_rejections');
const connectedAt = new Trend('frontiers_room_connected_at_ms', true);
const cleanRooms = new Counter('frontiers_clean_rooms');
const actorLatency = new Trend('frontiers_actor_ms', true);
const bothLatency = new Trend('frontiers_both_players_ms', true);

export const options = {
  scenarios: {
    games: { executor: 'per-vu-iterations', vus: ROOMS, iterations: 1,
      maxDuration: `${SECONDS + RAMP_SECONDS + 45}s`, gracefulStop: '10s' },
    health: { executor: 'constant-vus', exec: 'probeHealth', vus: 1,
      duration: `${SECONDS + RAMP_SECONDS}s`, gracefulStop: '6s' },
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: true, delayAbortEval: '15s' }],
    frontiers_errors: [{ threshold: 'count==0', abortOnFail: true, delayAbortEval: '15s' }],
    frontiers_health_errors: ['count==0'],
    frontiers_commands: ['count>0'],
    frontiers_connected_rooms: [`count==${ROOMS}`],
    // Late startup must not turn a hold test into a momentary connection spike.
    frontiers_room_connected_at_ms: [`max<=${(RAMP_SECONDS + SECONDS * .1) * 1000}`],
    frontiers_capacity_rejections: ['count==0'],
    frontiers_clean_rooms: [`count==${ROOMS}`],
    frontiers_both_players_ms: ['p(95)<1000'],
    'http_req_duration{name:GET /healthz}': ['p(95)<500'],
  },
};

// Synchronous HTTP runs in its own VU, so it cannot block a game's WebSocket callbacks.
export function probeHealth() {
  const started = Date.now();
  let response, failure = '';
  try {
    response = http.get(BASE + '/healthz', { timeout: '5s', redirects: 0,
      headers: { Origin: BASE }, tags: { name: 'GET /healthz' } });
    if (response.status !== 200) failure = response.error || `HTTP ${response.status}`;
    else if (response.json('status') !== 'ok') failure = 'Unexpected health response';
  } catch (error) { failure = error.message; }
  healthErrors.add(failure ? 1 : 0);
  if (failure) console.error(`${new Date().toISOString()} HEALTH probe: ${failure}; status=${response?.status ?? 'unknown'}`);
  else if (response.timings.duration > 1000)
    console.warn(`${new Date().toISOString()} HEALTH slow HTTP: duration_ms=${response.timings.duration.toFixed(1)}`);
  sleep(Math.max(0, 5 - (Date.now() - started) / 1000));
}

export default function () {
  // Scenario-local iteration IDs exclude the independent health VU.
  const ordinal = execution.scenario.iterationInTest;
  const scenarioStarted = execution.scenario.startTime;
  const endAt = scenarioStarted + (RAMP_SECONDS + SECONDS) * 1000;
  const launchAt = scenarioStarted + ordinal * RAMP_SECONDS * 1000 / Math.max(1, ROOMS - 1);
  sleep(Math.max(0, (launchAt - Date.now()) / 1000));
  commands.add(0); errors.add(0); matches.add(0); rooms.add(0); cleanRooms.add(0);
  connectedRooms.add(0); capacityRejections.add(0);
  const players = [0, 1].map(() => ({ jar: new http.CookieJar() }));
  const sockets = [];
  let code = '', states = [null, null], pending = null, cycle = 0, completedCycle = -1;
  let stopping = false, closing = false, connected = false, driveTimer, stopTimer, forceTimer, heartbeat, watchdog;
  const startedAt = Date.now(), lastReceived = [null, null];

  function close() {
    if (closing) return;
    closing = true;
    if (code && states.every(state => state?.game?.phase === 'finished')
        && states[0].game.version === states[1].game.version) cleanRooms.add(1);
    [driveTimer, stopTimer, forceTimer].forEach(timer => { if (timer !== undefined) clearTimeout(timer); });
    [heartbeat, watchdog].forEach(timer => { if (timer !== undefined) clearInterval(timer); });
    for (const socket of sockets) if (socket.readyState < 2) socket.close();
  }
  function problem(message, details = {}) {
    if (closing) return;
    errors.add(1);
    console.error(`${new Date().toISOString()} VU ${__VU}, test room ${code || '(not created)'}: ${message}`);
    console.error('DIAGNOSTIC ' + JSON.stringify({ ...details, vu: __VU, room: code,
      elapsed_ms: Date.now() - startedAt,
      sockets: sockets.map((socket, side) => ({ side, readyState: socket.readyState,
        last_message_age_ms: lastReceived[side] === null ? null : Date.now() - lastReceived[side],
        phase: states[side]?.game?.phase, version: states[side]?.game?.version })),
      pending: pending ? { side: pending.side, type: pending.type, version: pending.version,
        age_ms: Date.now() - pending.started, actor_seen: pending.actorSeen } : null }));
    close();
  }
  function request(side, path, body, name) {
    const params = { jar: players[side].jar, timeout: '5s', redirects: 0,
      headers: { 'Content-Type': 'application/json', Origin: BASE }, tags: { name } };
    const response = body === null ? http.get(BASE + path, params) : http.post(BASE + path, JSON.stringify(body), params);
    if (response.timings.duration > 1000) console.warn(`${new Date().toISOString()} VU ${__VU} slow HTTP: ${name}; status=${response.status}; duration_ms=${response.timings.duration.toFixed(1)}`);
    if (path === '/api/rooms' && response.status === 503 && String(response.body).includes('Сервер заполнен')) {
      capacityRejections.add(1);
      throw new Error('Room capacity limit reached (HTTP 503): existing rooms also occupy slots; this is not proof of CPU or memory exhaustion');
    }
    if (response.status < 200 || response.status >= 300)
      throw new Error(`${name}: HTTP ${response.status}; ${String(response.body).slice(0, 180)}`);
    return response.json();
  }
  function ready() {
    cycle++;
    states = players.map((player, side) => request(side, `/api/rooms/${code}/ready`,
      { leader: player.leader, deck: player.deck, ready: true }, 'POST /api/rooms/:code/ready'));
  }
  function queue(delay = THINK_MS) {
    if (closing || pending || driveTimer !== undefined) return;
    driveTimer = setTimeout(() => {
      driveTimer = undefined;
      try { drive(); } catch (error) { problem(error.message); }
    }, delay);
  }
  function send(side, move, cleanup = false) {
    const game = states[side].game;
    pending = { side, type: move.type, version: game.version, id: game.match_id, started: Date.now(), actorSeen: false, cleanup };
    sockets[side].send(JSON.stringify({ ...move, version: game.version }));
  }
  function drive() {
    if (closing || pending || sockets.some(socket => socket.readyState !== 1) || states.some(state => !state?.game)) return;
    const game = states[0].game, other = states[1].game;
    if (game.version !== other.version || game.phase !== other.phase || game.match_id !== other.match_id) return;
    if (stopping) {
      if (game.phase === 'finished') close();
      else send(0, { type: 'concede' }, true);
      return;
    }
    if (game.phase === 'finished') {
      if (completedCycle !== cycle) { matches.add(1); completedCycle = cycle; }
      ready(); queue(); return;
    }
    const side = game.phase === 'mulligan' ? (game.players[0].mulligan_done ? 1 : 0) : game.turn;
    const moves = states[side].game.moves;
    const choices = moves.filter(move => move.type === 'choose');
    const cards = moves.filter(move => move.type === 'play');
    const leaders = moves.filter(move => move.type === 'leader');
    const pass = moves.find(move => move.type === 'pass');
    const mulligan = moves.find(move => move.type === 'mulligan');
    const candidates = choices.length ? choices : mulligan ? [mulligan]
      : (pass && Math.random() < .08) ? [pass] : [...cards, ...leaders];
    const move = candidates.length ? candidates[Math.floor(Math.random() * candidates.length)] : pass;
    if (!move) throw new Error('No legal non-concede move');
    send(side, move);
  }
  function receive(side, raw) {
    if (closing) return;
    lastReceived[side] = Date.now();
    try {
      const message = JSON.parse(raw);
      if (message.type === 'error') return problem(`WebSocket: ${message.message}`);
      if (message.type !== 'state') return;
      if (states[side] && message.state.revision < states[side].revision) return;
      states[side] = message.state;
      if (pending) {
        const acknowledged = index => states[index]?.game?.version > pending.version
          && states[index].game.match_id === pending.id;
        if (side === pending.side && acknowledged(side) && !pending.actorSeen) {
          pending.actorSeen = true;
          if (!pending.cleanup) actorLatency.add(Date.now() - pending.started);
        }
        if (acknowledged(0) && acknowledged(1)) {
          if (!pending.cleanup) { bothLatency.add(Date.now() - pending.started); commands.add(1); }
          pending = null;
        }
      }
      queue(stopping ? 0 : THINK_MS);
    } catch (error) { problem(`State handling: ${error.message}`); }
  }

  try {
    if (Date.now() >= endAt) throw new Error('Load generator missed the scheduled room start');
    const catalog = request(0, '/api/catalog', null, 'GET /api/catalog');
    const presets = Object.values(catalog.decks).filter(deck => catalog.factions[deck.faction]?.playable);
    for (const [side, player] of players.entries()) {
      const preset = presets[(__VU - 1 + side) % presets.length];
      player.deck = preset.cards;
      player.leader = Object.entries(catalog.leaders).find(([, leader]) => leader.faction === preset.faction)[0];
    }
    code = request(0, '/api/rooms', { name: `Load-${__VU}-A` }, 'POST /api/rooms').code;
    rooms.add(1); console.log(`VU ${__VU}: test room ${code}`);
    request(1, `/api/rooms/${code}/join`, { name: `Load-${__VU}-B` }, 'POST /api/rooms/:code/join');
    ready();
    const url = BASE.replace(/^http/, 'ws') + `/ws/rooms/${code}`;
    for (let side = 0; side < 2; side++) {
      const socket = new WebSocket(url, [], { jar: players[side].jar,
        headers: { Origin: BASE }, tags: { name: 'WS /ws/rooms/:code' } });
      sockets.push(socket);
      socket.onmessage = event => receive(side, event.data);
      socket.onopen = () => {
        if (!connected && sockets.length === 2 && sockets.every(item => item.readyState === 1)) {
          connected = true;
          connectedRooms.add(1);
          connectedAt.add(Date.now() - scenarioStarted);
        }
        queue(0);
      };
      socket.onerror = event => problem(`WebSocket transport error: ${event.error || event.message || 'no transport details'}`,
        { side, event_type: event.type });
      socket.onclose = event => {
        if (!closing) problem(`Unexpected WebSocket close: code=${event.code}; reason=${event.reason || '(empty)'}`,
          { side, code: event.code, reason: event.reason || '' });
      };
    }
    heartbeat = setInterval(() => {
      if (!closing) for (const socket of sockets) if (socket.readyState === 1) socket.send(JSON.stringify({ type: 'ping' }));
    }, 25000);
    watchdog = setInterval(() => {
      if (pending && Date.now() - pending.started > TIMEOUT_MS) problem('Both clients did not acknowledge a command in 5s');
    }, 250);
    stopTimer = setTimeout(() => {
      stopping = true;
      if (driveTimer !== undefined) { clearTimeout(driveTimer); driveTimer = undefined; }
      queue(0);
      forceTimer = setTimeout(() => problem('Cleanup timed out; the test room may remain active'), TIMEOUT_MS + 2000);
    }, Math.max(0, endAt - Date.now()));
  } catch (error) { problem(error.message); }
}

export function handleSummary(data) {
  const values = metric => data.metrics[metric]?.values || {};
  const report = __ENV.REPORT || 'artifacts/load/summary.json';
  const rows = [`Frontiers: ${ROOMS} rooms / ${ROOMS * 2} players, think time ${THINK_MS} ms`,
    `Schedule: ramp ${RAMP_SECONDS}s, hold ${SECONDS}s, then cleanup`,
    `Created rooms: ${values('frontiers_rooms').count || 0}`,
    `Connected rooms (both players): ${values('frontiers_connected_rooms').count || 0}`,
    `Room capacity rejections: ${values('frontiers_capacity_rejections').count || 0}`,
    `Cleanly finished test rooms: ${values('frontiers_clean_rooms').count || 0}`,
    `Acknowledged commands: ${values('frontiers_commands').count || 0}`,
    `Naturally completed matches: ${values('frontiers_matches').count || 0}`,
    `Game errors: ${values('frontiers_errors').count || 0}`,
    `Health probe errors: ${values('frontiers_health_errors').count || 0}`];
  if (values('frontiers_connected_rooms').count === ROOMS) {
    const hold = Math.max(0, RAMP_SECONDS + SECONDS - values('frontiers_room_connected_at_ms').max / 1000);
    rows.push(`Time from last room connection to scheduled cleanup: ${hold.toFixed(1)}s (requires no intervening errors)`);
  }
  if (values('frontiers_capacity_rejections').count > 0)
    rows.push('Capacity limit reached: target concurrency was not achieved; check existing room occupancy before interpreting performance.');
  for (const metric of ['frontiers_actor_ms', 'frontiers_both_players_ms']) {
    const result = values(metric);
    rows.push(`${metric}: p50=${result.med?.toFixed(1) ?? '-'} ms, p95=${result['p(95)']?.toFixed(1) ?? '-'} ms, p99=${result['p(99)']?.toFixed(1) ?? '-'} ms`);
  }
  rows.push(`HTTP failures: ${((values('http_req_failed').rate || 0) * 100).toFixed(2)}%`, `JSON report: ${report}`);
  const failed = Object.entries(data.metrics).flatMap(([name, metric]) =>
    Object.entries(metric.thresholds || {}).filter(([, result]) => !result.ok).map(([condition]) => `${name}: ${condition}`));
  rows.push(failed.length ? `FAILED thresholds: ${failed.join('; ')}` : 'All thresholds passed');
  return { stdout: rows.join('\n') + '\n', [report]: JSON.stringify(data, null, 2) };
}
