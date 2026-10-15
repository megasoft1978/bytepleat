import assert from 'node:assert/strict';
import { startupAction, startupPath } from '../wdio.conf.js';

const invoke = async (command) => {
  const result = await browser.executeAsync(({ command }, done) => {
    window.__TAURI__.core.invoke(command).then(done, error => done({ invokeError: String(error) }));
  }, { command });
  if (result?.invokeError) throw new Error(result.invokeError);
  return result;
};

describe('Bytepleat startup arguments', () => {
  it(`opens the real WebView with --${startupAction} -- <runner-owned path>`, async () => {
    const expectedMode = startupAction === 'create' ? 'create' : startupAction;
    const tab = await $(`#tab-${expectedMode}`);
    await browser.waitUntil(async () => await tab.getAttribute('aria-selected') === 'true', {
      timeout: 15000,
      timeoutMsg: `The ${expectedMode} tab was not selected from process startup arguments`
    });

    const nativeSelection = await invoke('initial_selection');
    assert.equal(nativeSelection.action, startupAction);
    assert.deepEqual(nativeSelection.paths, [startupPath]);

    const selectedPathElement = await $('#selection .selected-item small');
    await selectedPathElement.waitForExist({ timeout: 15000 });
    const selectedPath = await selectedPathElement.getText();
    assert.equal(selectedPath, startupPath);
  });
});
