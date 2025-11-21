#!/usr/bin/env node
// scripts/read-js-cases.cjs
const fs = require("fs");
const path = require("path");
const Module = require("module");
const { pathToFileURL } = require("url");

;(async () => {
  const file = process.argv[2];
  if (!file) {
    console.error("Usage: node scripts/read-js-cases.cjs <file.js>");
    process.exit(2);
  }
  const absFile = path.resolve(file);
  const basedir = path.dirname(absFile);
  process.chdir(basedir);

  // helpers
  const noop = () => {};
  const deepFnProxy = new Proxy(noop, {
    get: () => deepFnProxy,
    apply: () => undefined,
    construct: () => ({})
  });
  const deepObjProxy = new Proxy({}, {
    get: () => deepObjProxy,
    apply: () => undefined,
    set: () => true,
    has: () => true
  });
  const expectObj = () => ({
    to: {
      equal: noop,
      be: { true: noop, false: noop, ok: noop, above: noop, below: noop },
      deep: { equal: noop },
      have: { length: noop, property: noop },
      include: noop,
      match: noop,
    },
  });

  // targeted stubs
  const STUBS = {
    "config.json": {},
    mongoose: {
      connect: async () => ({}),
      disconnect: async () => ({}),
      connection: { on: () => {}, once: () => {} },
      model: () => ({}),
      models: {},
      Schema: function () {},
      Types: { ObjectId: function () {} },
      createConnection: () => ({ on: () => {}, once: () => {}, close: () => {} }),
    },
    sinon: {
      useFakeTimers: () => ({ tick: () => {}, restore: () => {} }),
      restore: () => {},
      stub: () => ({ returns: () => {}, resolves: () => {}, rejects: () => {}, restore: () => {} }),
      spy: () => ({ called: false, calledOnce: false, restore: () => {} }),
      fake: { timers: () => ({ tick: () => {}, restore: () => {} }) },
    },
    "@sinonjs/fake-timers": {
      install: () => ({ tick: () => {}, uninstall: () => {} }),
      withGlobal: () => ({ install: () => ({ tick: () => {}, uninstall: () => {} }) }),
      default: { install: () => ({ tick: () => {}, uninstall: () => {} }) },
    },
    chai: {
      expect: expectObj,
      assert: { equal: noop, deepEqual: noop, ok: noop, isTrue: noop, isFalse: noop },
      should: () => {},
    },
    expect: expectObj,
    assert: { equal: noop, deepEqual: noop, ok: noop, isTrue: noop, isFalse: noop },
  };

  // require hook (mock ที่หาย + proxy สำหรับโมดูล/relative ที่หาไม่เจอ)
  const origLoad = Module._load;
  Module._load = function (request, parent, isMain) {
    try {
      // config.json
      if (request.endsWith("config.json") || request.includes("/config.json")) {
        try {
          const resolved = Module._resolveFilename(request, parent, isMain);
          if (fs.existsSync(resolved)) return origLoad.apply(this, arguments);
        } catch (_) {}
        return STUBS["config.json"];
      }
      if (request in STUBS) return STUBS[request];

      // relative requires
      if (request.startsWith("./") || request.startsWith("../")) {
        try {
          const resolved = Module._resolveFilename(request, parent, isMain);
          if (fs.existsSync(resolved)) return origLoad.apply(this, arguments);
          return deepObjProxy;
        } catch (_) {
          return deepObjProxy;
        }
      }

      // bare module ids (lodash/moment/etc.)
      try {
        const resolved = Module._resolveFilename(request, parent, isMain);
        if (fs.existsSync(resolved)) return origLoad.apply(this, arguments);
        return deepObjProxy;
      } catch (_) {
        return deepObjProxy;
      }
    } catch (e) {
      throw e;
    }
  };

  // load target file: try CJS then ESM
  let mod = null;
  try {
    mod = require(absFile);
  } catch (_e1) {
    try {
      const url = pathToFileURL(absFile).href;
      const esm = await import(url);
      mod = esm;
    } catch (e2) {
      console.error("Cannot load JS module:", e2.message);
      process.exit(3);
    }
  }

  let data = (mod && (mod.default ?? mod.cases ?? mod)) || [];
  if (!Array.isArray(data) && Array.isArray(global.CASES)) data = global.CASES;
  if (!Array.isArray(data)) data = [data];

  console.log(JSON.stringify(data));
})().catch(err => {
  console.error(err && err.stack || err);
  process.exit(3);
});
