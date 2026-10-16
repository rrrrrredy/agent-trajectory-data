#!/usr/bin/env node
// Optional publication export. Requires Node 22+ and marked 17.0.5; no runtime service.
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {marked} = require('marked');

const root = path.resolve(__dirname, '..');
const sourceRoot = path.join(root, 'corpora/ai-industry');
const output = process.argv[2];
if (!output) throw new Error('Usage: node scripts/export_ai_industry_site.cjs ../research-toolkit/docs/materials');
const destination = path.resolve(output);
const sourceRevision = execFileSync('git', ['rev-parse', 'HEAD'], {cwd: root, encoding: 'utf8'}).trim();
const repository = 'https://github.com/rrrrrredy/agent-trajectory-data';
const sourceUrl = repository + '/blob/' + sourceRevision + '/corpora/ai-industry/';
const archive = repository + '/releases/tag/ai-industry-corpus-v1';
const site = 'https://rrrrrredy.github.io/research-toolkit/materials/';
const routes = new Map([
  ['BROWSE.md', 'index.html'], ['BROWSE.zh-CN.md', 'index.zh-CN.html'],
  ['README.md', 'guide.html'], ['README.zh-CN.md', 'guide.zh-CN.html'],
  ['recovered/README.md', 'recovered/index.html'],
  ['recovered/README.zh-CN.md', 'recovered/index.zh-CN.html'],
  ['recovery-notes.zh-CN.md', 'recovery-notes.zh-CN.html'],
]);
for (const folder of ['reading', 'recovered']) {
  for (const name of fs.readdirSync(path.join(sourceRoot, folder)).sort()) {
    if (/^D-\d+\.md$/.test(name)) routes.set(folder + '/' + name, folder + '/' + name.replace('.md', '.zh-CN.html'));
  }
}
const pairs = [
  ['index.html', 'index.zh-CN.html'], ['guide.html', 'guide.zh-CN.html'],
  ['recovered/index.html', 'recovered/index.zh-CN.html'],
];
const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const relative = (from, to) => path.posix.relative(path.posix.dirname(from), to);
const descriptions = {};

for (const [source, target] of routes) {
  const markdown = fs.readFileSync(path.join(sourceRoot, source), 'utf8');
  const title = markdown.split('\n')[0].replace(/^#\s+/, '').trim();
  const zh = target.includes('.zh-CN.');
  const catalog = source.startsWith('BROWSE');
  const description = zh ? title + '。保留已有材料、来源与历史版本，以及未核实和缺失内容说明。' : title + '. Existing material with source links, historical versions and unverified labels retained.';
  descriptions['materials/' + target] = description;
  // Join blank-separated table rows for display only; original Markdown stays unchanged.
  let content = marked.parse(markdown.replace(/\|\r?\n(?:[ \t]*\r?\n)+(?=\|)/g, '|\n'), {gfm: true});
  content = content.replace(/href="([^"]*)"/g, (whole, href) => {
    if (!href || /^(?:[a-z][a-z\d+.-]*:|#|\/)/i.test(href)) return whole;
    const [file, fragment] = href.split('#');
    const original = path.posix.normalize(path.posix.join(path.posix.dirname(source), file));
    const mapped = routes.get(original);
    const resolved = mapped ? relative(target, mapped) : sourceUrl + original;
    return 'href="' + escape(resolved) + (fragment ? '#' + fragment : '') + '"';
  });
  content = content.replace(/<table>/g, '<div class="table-scroll" tabindex="0" role="region" aria-label="' + (zh ? '表格，可横向滚动' : 'Table; scroll horizontally') + '"><table>').replace(/<\/table>/g, '</table></div>');
  const pair = pairs.find(pair => pair.includes(target));
  const alternates = pair ? pair.map((file, i) => '<link rel="alternate" hreflang="' + (i ? 'zh-CN' : 'en') + '" href="' + site + file.replace(/index\.html$/, '') + '">').join('\n') + '\n<link rel="alternate" hreflang="x-default" href="' + site + pair[0].replace(/index\.html$/, '') + '">' : '';
  const home = relative('materials/' + target, zh ? 'index.zh-CN.html' : 'index.html');
  const assets = relative('materials/' + target, 'assets');
  const text = `<!DOCTYPE html>
<html lang="${zh ? 'zh-CN' : 'en'}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escape(title)} · Research Toolkit</title>
<meta name="description" content="${escape(description)}">
<link rel="canonical" href="${site + target.replace(/index\.html$/, '')}">
${alternates}
<link rel="stylesheet" href="${assets}/showcase.css?v=site-20261015">
<link rel="stylesheet" href="${assets}/materials.css">
<script src="${assets}/reading-preferences.js?v=site-20261015"></script></head>
<body><main class="report-shell materials-reader${catalog ? ' materials-catalog' : ''}">
<nav class="report-nav" aria-label="${zh ? '阅读导航' : 'Reading navigation'}"><a data-home-link href="${home}">Research Toolkit</a><a href="${relative(target, 'index.zh-CN.html')}">中文目录</a><a href="${relative(target, 'index.html')}">English catalog</a></nav>
<article class="report-article">${content}</article>
<footer class="materials-provenance"><a href="${sourceUrl + source}">${zh ? '原始 Markdown' : 'Original Markdown'}</a> · <a href="${archive}">${zh ? '全部历史版本' : 'All historical versions'}</a></footer>
</main></body></html>
`;
  const file = path.join(destination, target);
  fs.mkdirSync(path.dirname(file), {recursive: true});
  fs.writeFileSync(file, text);
}
fs.writeFileSync(path.join(destination, 'pages.json'), JSON.stringify({sourceRevision, descriptions, pairs: pairs.map(pair => pair.map(file => 'materials/' + file))}, null, 2) + '\n');
console.log('Exported ' + routes.size + ' static pages from existing Markdown to ' + destination);
