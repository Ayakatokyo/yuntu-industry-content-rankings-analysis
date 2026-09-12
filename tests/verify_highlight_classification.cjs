// Exercise the shipped category handlers without a browser or report assets.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../scripts/templates/final-report-template.html'), 'utf8');
const panels = new Map();
const modes = [{tabs: []}, {tabs: []}];
const tabs = modes.flatMap((mode, m) => ['portrait', 'product', 'other'].map((category, i) => {
  const id = `${m}-${category}`;
  panels.set(id, {hidden: i !== 0});
  const tab = {
    attrs: {'data-highlight-category-target': id, 'aria-selected': String(i === 0)}, events: {},
    closest(selector) { return selector === '[data-highlight-classification-panel]' ? mode : brand; },
    getAttribute(key) { return this.attrs[key]; },
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(key, fn) { this.events[key] = fn; },
    focus() { this.focused = true; }
  };
  mode.tabs.push(tab);
  return tab;
}));
const brand = {querySelectorAll() { return tabs; }};
modes.forEach(mode => {mode.querySelectorAll = () => mode.tabs;});
const context = {highlightTabs: tabs, paginateHighlightPanel() {},
  document: {getElementById(id) { return panels.get(id); }}};
vm.runInNewContext(source.slice(source.indexOf('function activateHighlightCategory('),
  source.indexOf('function activateHighlightClassification(')), context);
// Clicking a standard category must not clear a batch category.
modes[0].tabs[1].events.click();
assert.strictEqual(panels.get('0-product').hidden, false);
assert.strictEqual(panels.get('1-portrait').hidden, false);
assert.strictEqual(modes[1].tabs[0].attrs['aria-selected'], 'true');
// Keyboard navigation wraps inside the active classification mode.
modes[0].tabs[2].events.keydown({key: 'ArrowRight', preventDefault() {}});
assert.strictEqual(modes[0].tabs[0].focused, true);
modes[1].tabs[0].events.keydown({key: 'End', preventDefault() {}});
assert.strictEqual(modes[1].tabs[2].focused, true);
assert.strictEqual(panels.get('0-portrait').hidden, false);
assert.strictEqual(panels.get('1-other').hidden, false);
console.log('classification click and keyboard isolation passed');
