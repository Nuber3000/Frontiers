"use strict";

const runtime = "/static/pyodide-0.29.3/";
let dispatch, initialization, botTimer;

async function initialize() {
  importScripts(`${runtime}pyodide.js`);
  const [python, response] = await Promise.all([
    loadPyodide({indexURL: runtime}),
    fetch("/api/local-engine"),
  ]);
  if (!response.ok) throw new Error("Не удалось загрузить правила игры.");
  python.FS.mkdir("/frontiers");
  for (const [name, source] of Object.entries(await response.json())) {
    python.FS.writeFile(`/frontiers/${name}`, source);
  }
  python.runPython("import sys\nsys.path.insert(0, '/')\nfrom frontiers.local_match import LocalMatch\nmatch = LocalMatch()");
  dispatch = python.runPython("match.dispatch");
}

function handle(request, id) {
  try {
    const result = JSON.parse(dispatch(JSON.stringify(request)));
    postMessage({id, ...result});
    if (!result.error) {
      clearTimeout(botTimer);
      if (result.bot_turn) botTimer = setTimeout(() => handle({type: "bot"}), 700);
    }
  } catch (error) {
    console.error(error);
    postMessage({id, error: "Ошибка локального движка. Откройте новый матч."});
  }
}

self.onmessage = async ({data: {id, request}}) => {
  try {
    initialization ??= initialize();
    await initialization;
    handle(request, id);
  } catch (error) {
    console.error(error);
    postMessage({id, error: "Не удалось запустить бота. Проверьте загрузку игры и попробуйте ещё раз."});
  }
};
