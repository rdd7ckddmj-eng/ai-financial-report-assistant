// Run with: node --test tests/research_case_storage.test.mjs
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

const app = readFileSync(new URL('../src/app.py', import.meta.url), 'utf8');
const component = app.split('_RESEARCH_CASE_STORAGE = st.components.v2.component(')[1]
  .split('_CASH_GAME_PROGRESS_STORAGE =')[0];
const source = component.match(/js="""([\s\S]*?)"""/)[1]
  .replace('export default function', 'function render');
const snapshot = (revision) => ({schema_version: '1.0', store_revision: revision, cases: {}});

function run(stored, data = {}, failWrite = false) {
  let encoded = stored ? JSON.stringify(stored) : null;
  const events = {};
  let writes = 0;
  const context = {
    TextEncoder,
    localStorage: {
      getItem: () => encoded,
      setItem: (_key, value) => {
        if (failWrite) throw new Error('quota');
        encoded = value;
        writes++;
      },
    },
    props: {
      data: {storage_key: 'test', known_storage_status: 'available',
        known_snapshot: snapshot(2), write_enabled: true,
        base_revision: 1, writer_id: 'writer-a', ...data},
      setStateValue: (key, value) => { events[key] = JSON.parse(JSON.stringify(value)); },
    },
  };
  vm.runInNewContext(source + '\nrender(props);', context);
  return {events, writes, stored: encoded && JSON.parse(encoded)};
}

test('successful write explicitly acknowledges an otherwise identical known snapshot', () => {
  const result = run(snapshot(1));
  assert.deepEqual(result.events, {snapshot: snapshot(2), storage_status: 'available'});
  assert.equal(result.writes, 1);
});
test('passive render after acknowledgement emits nothing and writes nothing', () => {
  const result = run(snapshot(2), {write_enabled: false});
  assert.deepEqual(result.events, {});
  assert.equal(result.writes, 0);
});
test('same writer can replay a completed write and receive acknowledgement', () => {
  const result = run({...snapshot(2), _wfz_writer_id: 'writer-a'});
  assert.deepEqual(result.events.snapshot, snapshot(2));
});
test('another writer newer revision is returned without being overwritten', () => {
  const result = run({...snapshot(3), _wfz_writer_id: 'writer-b'});
  assert.equal(result.writes, 0);
  assert.deepEqual(result.events.snapshot, snapshot(3));
});
test('quota failure reports unavailable without claiming pending data was saved', () => {
  const result = run(snapshot(1), {}, true);
  assert.equal(result.events.storage_status, 'unavailable');
  assert.deepEqual(result.events.snapshot, snapshot(1));
  assert.equal(result.writes, 0);
});
