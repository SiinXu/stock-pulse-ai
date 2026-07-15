import http from 'node:http';

const port = Number(process.argv[2] || 18101);
const models = [
  { id: 'fake-report-model', object: 'model', owned_by: 'dsa-e2e' },
  { id: 'fake-vision-model', object: 'model', owned_by: 'dsa-e2e' },
  { id: 'fake-agent-model', object: 'model', owned_by: 'dsa-e2e' },
];
const ollamaModels = [
  { name: 'llama3.2:latest', model: 'llama3.2:latest' },
  { name: 'qwen2.5:latest', model: 'qwen2.5:latest' },
];
const observedRequests = [];

function sendJson(response, status, payload) {
  response.writeHead(status, { 'content-type': 'application/json' });
  response.end(JSON.stringify(payload));
}

function readJson(request, callback) {
  let body = '';
  request.setEncoding('utf8');
  request.on('data', (chunk) => { body += chunk; });
  request.on('end', () => {
    try {
      callback(body ? JSON.parse(body) : {});
    } catch {
      callback({});
    }
  });
}

const server = http.createServer((request, response) => {
  console.log(`[fake-provider] ${request.method} ${request.url}`);
  const pathname = new URL(request.url || '/', `http://${request.headers.host || '127.0.0.1'}`).pathname;
  if (request.method === 'DELETE' && pathname === '/__requests') {
    observedRequests.length = 0;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (request.method === 'GET' && pathname === '/__requests') {
    sendJson(response, 200, { requests: observedRequests });
    return;
  }
  observedRequests.push({
    method: request.method,
    path: pathname,
    authorization: Boolean(request.headers.authorization),
  });
  if (pathname === '/health') {
    sendJson(response, 200, { ok: true });
    return;
  }
  if (request.method === 'GET' && pathname.replace(/\/$/, '') === '/v1/models') {
    sendJson(response, 200, { object: 'list', data: models });
    return;
  }
  if (request.method === 'GET' && pathname.replace(/\/$/, '') === '/api/tags') {
    sendJson(response, 200, { models: ollamaModels });
    return;
  }
  if (request.method === 'POST' && pathname.replace(/\/$/, '') === '/v1/chat/completions') {
    readJson(request, (payload) => {
      const model = payload.model || 'fake-report-model';
      const prompt = Array.isArray(payload.messages)
        ? payload.messages.map((message) => String(message?.content || '')).join('\n')
        : '';
      const content = prompt.includes('DSA_GENERATION_BACKEND_SMOKE_OK')
        ? 'DSA_GENERATION_BACKEND_SMOKE_OK'
        : prompt.includes('"backend_smoke": "passed"')
          ? '{"ok": true, "backend_smoke": "passed"}'
          : 'ok';
      sendJson(response, 200, {
        id: 'chatcmpl-dsa-e2e',
        object: 'chat.completion',
        created: 0,
        model,
        choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      });
    });
    return;
  }
  if (request.method === 'POST' && pathname.replace(/\/$/, '') === '/api/chat') {
    readJson(request, (payload) => {
      sendJson(response, 200, {
        model: payload.model || 'llama3.2:latest',
        created_at: '2026-01-01T00:00:00Z',
        message: { role: 'assistant', content: 'OK' },
        done: true,
        done_reason: 'stop',
        total_duration: 1,
        load_duration: 1,
        prompt_eval_count: 1,
        prompt_eval_duration: 1,
        eval_count: 1,
        eval_duration: 1,
      });
    });
    return;
  }
  if (request.method === 'POST' && pathname.replace(/\/$/, '') === '/api/generate') {
    readJson(request, (payload) => {
      sendJson(response, 200, {
        model: payload.model || 'llama3.2:latest',
        created_at: '2026-01-01T00:00:00Z',
        response: 'OK',
        done: true,
        done_reason: 'stop',
        context: [],
        total_duration: 1,
        load_duration: 1,
        prompt_eval_count: 1,
        prompt_eval_duration: 1,
        eval_count: 1,
        eval_duration: 1,
      });
    });
    return;
  }
  sendJson(response, 404, { error: { message: 'not found' } });
});

server.listen(port, '127.0.0.1', () => {
  console.log(`[fake-provider] listening on 127.0.0.1:${port}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
