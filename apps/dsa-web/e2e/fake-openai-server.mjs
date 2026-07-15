import http from 'node:http';

const port = Number(process.argv[2] || 18101);
const models = [
  { id: 'fake-report-model', object: 'model', owned_by: 'dsa-e2e' },
  { id: 'fake-vision-model', object: 'model', owned_by: 'dsa-e2e' },
  { id: 'fake-agent-model', object: 'model', owned_by: 'dsa-e2e' },
];

function sendJson(response, status, payload) {
  response.writeHead(status, { 'content-type': 'application/json' });
  response.end(JSON.stringify(payload));
}

const server = http.createServer((request, response) => {
  if (request.url === '/health') {
    sendJson(response, 200, { ok: true });
    return;
  }
  if (request.method === 'GET' && request.url?.replace(/\/$/, '') === '/v1/models') {
    sendJson(response, 200, { object: 'list', data: models });
    return;
  }
  if (request.method === 'POST' && request.url?.replace(/\/$/, '') === '/v1/chat/completions') {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => { body += chunk; });
    request.on('end', () => {
      let model = 'fake-report-model';
      try {
        model = JSON.parse(body).model || model;
      } catch {
        // The endpoint deliberately remains deterministic for malformed probes.
      }
      sendJson(response, 200, {
        id: 'chatcmpl-dsa-e2e',
        object: 'chat.completion',
        created: 0,
        model,
        choices: [{ index: 0, message: { role: 'assistant', content: 'ok' }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      });
    });
    return;
  }
  sendJson(response, 404, { error: { message: 'not found' } });
});

server.listen(port, '127.0.0.1');

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
