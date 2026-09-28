// Empty application: it serves the test harness (see ../../harness-contract.md) and nothing else.
// The whole suite must be red against it; a test that passes here proves nothing.
import { createServer } from 'node:http';

const port = Number(process.env.PORT ?? 3999);
const page = '<!doctype html><html><head><meta charset="utf-8"><title>empty</title></head>'
  + '<body><main></main></body></html>';

createServer((req, res) => {
  if (req.method === 'POST' && req.url?.startsWith('/__test__/')) {
    res.writeHead(204).end();
    return;
  }
  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(page);
}).listen(port, () => console.log(`empty application on http://localhost:${port}`));
