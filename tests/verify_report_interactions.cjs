const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
data.scripts.forEach((source) => new vm.Script(source));
function node(attrs, text = '') {
  const classes = new Set((attrs.class || '').split(' '));
  return {attrs: {...attrs}, id: attrs.id, textContent: text, hidden: 'hidden' in attrs, events: {},
    getAttribute(k) { return this.attrs[k] ?? null; }, setAttribute(k, v) { this.attrs[k] = String(v); },
    addEventListener(k, f) { this.events[k] = f; }, focus() { this.focused = true; }, scrollIntoView() {},
    classList: {add(k) { classes.add(k); }, remove(k) { classes.delete(k); }, contains(k) { return classes.has(k); }} };
}
const tabs = data.tabs.map(x => node(x));
const panels = data.panels.map(x => node(x));
const brandRoot = {querySelectorAll(selector) { return selector === '[data-script-brand-tab]' ? tabs : panels; }};
const formulaScript = data.scripts.find(x => x.includes("document.querySelectorAll('[data-script-brand-dashboard]')"));
const brandStart = formulaScript.indexOf("document.querySelectorAll('[data-script-brand-dashboard]')");
const brandEnd = formulaScript.indexOf("document.querySelectorAll('[data-script-formula]')", brandStart);
vm.runInNewContext(formulaScript.slice(brandStart, brandEnd), {document: {querySelectorAll() { return [brandRoot]; }}});
for (const tab of tabs) {
  tab.events.click();
  assert.deepStrictEqual(panels.filter(x => !x.hidden).map(x => x.id), [tab.attrs['data-script-brand-tab']]);
  assert.strictEqual(tabs.filter(x => x.attrs['aria-selected'] === 'true').length, 1);
}
tabs[6].events.keydown({key: 'ArrowRight', preventDefault() {}});
assert.strictEqual(panels[0].hidden, false);
tabs[0].events.keydown({key: 'End', preventDefault() {}});
assert.strictEqual(panels[6].hidden, false);
const highlightBrandTabs = data.highlightTabs.map(x => node(x));
const highlightPanels = data.highlightPanels.map(x => ({...node(x), querySelector() { return null; }}));
const highlightScript = data.scripts.find(x => x.includes('function activateHighlightBrand('));
const hStart = highlightScript.indexOf('function activateHighlightBrand(');
const hEnd = highlightScript.indexOf("document.querySelectorAll('[data-highlight-pagination]')", hStart);
vm.runInNewContext(highlightScript.slice(hStart, hEnd), {highlightBrandTabs,
  document: {getElementById(id) { return highlightPanels.find(x => x.id === id); }}});
for (const tab of highlightBrandTabs) {
  tab.events.click();
  assert.deepStrictEqual(highlightPanels.filter(x => !x.hidden).map(x => x.id), [tab.attrs['data-highlight-brand-target']]);
}
highlightBrandTabs[6].events.keydown({key: 'Home', preventDefault() {}});
assert.strictEqual(highlightPanels[0].hidden, false);
const evidenceScript = data.scripts.find(x => x.includes('function clearScriptEvidence('));
const start = evidenceScript.indexOf('function scriptPrefersReducedMotion(');
const end = evidenceScript.indexOf('var scriptTab =', start);
const context = {window: {matchMedia() { return {matches: true}; }}};
vm.createContext(context);
vm.runInContext(evidenceScript.slice(start, end), context);
let checked = 0, located = 0;
for (const vector of data.vectors) {
  const buttons = vector.buttons.map(x => node(x));
  const spans = vector.spans.map(x => node(x.attrs, x.text));
  const status = node({});
  const panel = {querySelector() { return status; }, querySelectorAll(selector) {
    if (selector === '.script-evidence-highlight.is-evidence-active') return spans.filter(x => x.classList.contains('is-evidence-active'));
    if (selector === '[data-script-formula][aria-pressed="true"]') return buttons.filter(x => x.attrs['aria-pressed'] === 'true');
    if (selector === '[data-script-evidence-ref]') return spans;
    if (selector === '[data-script-formula]') return buttons;
    throw new Error(selector);
  }};
  for (const button of buttons) {
    const refs = JSON.parse(button.attrs['data-script-evidence-refs']);
    context.highlightScriptEvidence(panel, refs);
    const expected = spans.filter(x => JSON.parse(x.attrs['data-script-span-refs']).some(ref => refs.includes(ref)));
    const actual = spans.filter(x => x.classList.contains('is-evidence-active'));
    assert.deepStrictEqual(actual, expected);
    if (refs.length) {
      assert.ok(actual.length, `unlocatable refs in ${vector.id}`);
      const length = actual.reduce((n, x) => n + x.textContent.length, 0);
      assert.ok(length < vector.textLength, `whole-script highlight in ${vector.id}`);
      located++;
    } else assert.strictEqual(actual.length, 0);
    checked++;
  }
}
console.log(JSON.stringify({scriptBrandTabs: tabs.length, brandClickAndKeyboard: 'passed', highlightBrandSwitch: 'passed', formulaButtonsChecked: checked, formulasWithExactTargets: located, javascriptSyntax: 'passed'}, null, 2));
