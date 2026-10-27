const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function setup() {
  let timers = new Map(), id = 0, calls = [], players = [];
  const listeners = {};
  const video = { currentTime: 0, volume: 0.1, paused: false, seeking: false, playbackRate: 1,
    addEventListener(name, fn) { listeners[name] = fn; } };
  class Audio {
    constructor() { this.paused = true; players.push(this); }
    play() { this.paused = false; return Promise.resolve(); }
    pause() { this.paused = true; }
    removeAttribute() { this.src = ''; }
    load() {}
  }
  let now = 0;
  const context = { Audio, AbortController, performance: { now: () => now }, console: { debug() {}, warn() {} },
    setTimeout(fn, delay) { timers.set(++id, { fn, delay }); return id; },
    clearTimeout(i) { timers.delete(i); }, setInterval() {},
    document: { readyState: 'loading', addEventListener() {}, getElementById() { return null; },
      querySelector() { return video; }, querySelectorAll() { return []; } },
    fetch(url, options) { return new Promise((resolve, reject) => calls.push({ options, resolve, reject })); }
  };
  const file = path.join(__dirname, '../extension/content.js');
  const source = fs.readFileSync(file, 'utf8').replace(/\}\)\(\);\s*$/, `globalThis.api = {
    findVideoElement, enqueue, pump, resetSession, handleCaptionUpdate, flushCaption, extractOnlyNewWords,
    disable() { isEnabled = false; resetSession(); },
    state() { return { jobs, active, currentJob, pendingWordBuffer, spokenHistory, retryUntil }; }
  }; })();`);
  vm.runInNewContext(source, context); context.api.findVideoElement();
  const resolve = async (i, text) => {
    calls[i].resolve({ ok: true, json: async () => ({ audio_base64: 'AA==', translated_text: text }) });
    for (let n = 0; n < 8; n++) await Promise.resolve();
  };
  return { advance(ms) { now += ms; }, api: context.api, video, calls, resolve, player: players[0], listeners, timers };
}
test('responses completing out of order retain caption order', async () => {
  const h = setup(); h.api.enqueue('first', 0); h.api.enqueue('second', 0);
  await h.resolve(1, 'second'); assert.equal(h.api.state().currentJob, null);
  await h.resolve(0, 'first'); assert.equal(h.api.state().currentJob.text, 'first');
  h.player.onended(); assert.equal(h.api.state().currentJob.text, 'second');
});
test('late response after seeking cannot play or replace new speech', async () => {
  const h = setup(); h.api.enqueue('old', 0); h.listeners.seeking();
  assert.equal(h.calls[0].options.signal.aborted, true);
  h.video.currentTime = 50; h.api.enqueue('new', 50);
  await h.resolve(0, 'old'); assert.equal(h.api.state().currentJob, null);
  await h.resolve(1, 'new'); assert.equal(h.api.state().currentJob.text, 'new');
});
test('disable rejects in-flight results and clears capture timers', async () => {
  const h = setup(); h.api.handleCaptionUpdate('pending words'); h.api.enqueue('old', 0);
  h.api.disable(); await h.resolve(0, 'old');
  assert.equal(h.api.state().currentJob, null); assert.equal(h.api.state().pendingWordBuffer, '');
  assert.equal(h.timers.size, 0);
});
test('old audio and work expire instead of building a backlog', async () => {
  const h = setup(); h.api.enqueue('old', 0); h.video.currentTime = 8;
  await h.resolve(0, 'old'); h.api.pump();
  assert.equal(h.api.state().jobs.length, 0); assert.equal(h.api.state().currentJob, null);
});
test('queue and parallel requests stay bounded under burst load', () => {
  const h = setup(); for (let i = 0; i < 100; i++) h.api.enqueue('phrase ' + i, 0);
  assert.ok(h.api.state().jobs.length <= 3); assert.ok(h.calls.length <= 2);
});
test('response while video paused waits; resume plays and volume is restored exactly', async () => {
  const h = setup(); h.api.enqueue('first', 0); h.video.paused = true; h.listeners.pause();
  await h.resolve(0, 'first'); assert.equal(h.api.state().currentJob, null);
  h.video.paused = false; h.listeners.play(); assert.equal(h.player.paused, false);
  assert.ok(h.video.volume < 0.1); h.listeners.pause(); assert.equal(h.video.volume, 0.1);
  h.api.resetSession(); assert.equal(h.video.volume, 0.1);
});
test('rolling captions accumulate new words without losing the earlier pending phrase', () => {
  const h = setup(); h.api.handleCaptionUpdate('Hola cómo'); h.api.handleCaptionUpdate('cómo estás');
  assert.equal(h.api.state().pendingWordBuffer, 'Hola cómo estás');
  h.api.flushCaption(); assert.equal(JSON.parse(h.calls[0].options.body).text, 'Hola cómo estás');
});
test('continuous caption updates have a non-resetting maximum wait', () => {
  const h = setup(); h.api.handleCaptionUpdate('one');
  const max = [...h.timers].find(([_, t]) => t.delay === 700)[0];
  h.api.handleCaptionUpdate('one two'); h.api.handleCaptionUpdate('one two three');
  assert.ok(h.timers.has(max)); h.timers.get(max).fn();
  assert.equal(h.calls.length, 1); assert.equal(JSON.parse(h.calls[0].options.body).text, 'one two three');
});
test('Unicode accents survive overlap removal', () => {
  const h = setup(); assert.equal(h.api.extractOnlyNewWords('el niño está', 'niño está aquí'), 'aquí');
});
test('video speed affects dubbing playback rate', async () => {
  const h = setup(); h.video.playbackRate = 1.5; h.api.enqueue('first', 0); await h.resolve(0, 'first');
  assert.equal(h.player.playbackRate, 1.5);
});

test('rate limit pauses requests and resumes only with fresh captions', async () => {
  const h = setup(); h.api.enqueue('old', 0);
  h.calls[0].resolve({ ok: false, status: 503, headers: { get: () => '60' },
    json: async () => ({ detail: { code: 'rate_limited', message: 'Límite alcanzado', retry_after: 60 } }) });
  for (let n = 0; n < 12; n++) await Promise.resolve();
  for (let n = 0; n < 20; n++) h.api.enqueue('during cooldown', 0);
  h.api.pump(); assert.equal(h.calls.length, 1); assert.equal(h.api.state().jobs.length, 0);
  h.advance(59000); h.api.enqueue('too soon', 0); assert.equal(h.calls.length, 1);
  h.advance(1001); h.video.currentTime = 61; h.api.enqueue('fresh', 61);
  assert.equal(h.calls.length, 2); await h.resolve(1, 'fresh');
  assert.equal(h.api.state().currentJob.text, 'fresh');
});
test('server error and request timeout also back off instead of looping', async () => {
  for (const timeout of [false, true]) {
    const h = setup(); h.api.enqueue('old', 0);
    if (timeout) h.calls[0].reject(Object.assign(new Error('timeout'), { name: 'AbortError' }));
    else h.calls[0].resolve({ ok: false, status: 500, json: async () => ({}) });
    for (let n = 0; n < 12; n++) await Promise.resolve();
    h.api.enqueue('next', 0); h.api.pump();
    assert.equal(h.calls.length, 1); assert.ok(h.api.state().retryUntil > 0);
  }
});
test('caption context accompanies short chunks for source language detection', () => {
  const h = setup(); h.api.handleCaptionUpdate('Hoy vamos a aprender cómo resolver tareas complejas.');
  h.api.handleCaptionUpdate('tareas complejas. y actúa'); h.api.flushCaption();
  const body = JSON.parse(h.calls[1].options.body);
  assert.equal(body.text, 'y actúa');
  assert.ok(body.context.includes('Hoy vamos a aprender'));
  assert.equal(body.source_lang, 'auto');
});
