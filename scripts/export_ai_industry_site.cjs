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

// Display only: keep source Markdown and undecodable captures unchanged.
function renderBody(text, render, zh) {
  text = text.replace(/\r\n?/g, '\n');
  const blocks = [];
  const hold = (html, block = true) => {
    const key = '<!--material-fragment-' + blocks.push(html) + '-->';
    return block ? '\n\n' + key + '\n\n' : key;
  };
  const missing = (label, originalHtml) => hold('<div class="material-gap"><p>' + label + '</p><details class="material-fragment"><summary>' +
    (zh ? '查看原始片段' : 'View original fragment') + '</summary>' + originalHtml + '</details></div>');
  const tableMissing = zh ? '表格缺失：现有片段无法完整还原。' : 'Table unavailable: the retained fragment cannot be fully reconstructed.';
  const diagramMissing = zh ? '图表缺失：材料只保留引用，未保存可显示的图表内容。' : 'Diagram unavailable: only a reference was retained, without displayable diagram content.';
  // Code examples are not document formatting directives.
  text = text.replace(/^(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1[ \t]*$/gm, raw => hold(render(raw)));
  text = text.replace(/(?:未能展开此表；以下保留该处原始捕获内容。\s*)?<pre>[\s\S]*?<\/pre>/g, raw =>
    raw.includes(':::table') ? missing(tableMissing, raw.replace(/^未能展开此表；以下保留该处原始捕获内容。\s*/, '<p>未能展开此表；以下保留该处原始捕获内容。</p>')) : hold(raw));
  text = text.replace(/`[^`\n]+`/g, raw => hold(marked.parseInline(raw), false));
  // These rows end in an explicitly truncated formatting token. Do not let GFM pad them with invented empty cells.
  text = text.replace(/^[ \t]*\|[^\n]*(?::::(?:par|parag)\b|:\[font\]\{size=$)[^\n]*$/gm,
    raw => missing(tableMissing, '<pre>' + escape(raw) + '</pre>'));
  text = text.replace(/:::(drawio|attachment)\{[^}\n]*\}|:\[data2chart\]\{[^}\n]*\}/g, (raw, kind) =>
    missing(kind === 'attachment' ? (zh ? '附件缺失：材料只保留附件引用。' : 'Attachment unavailable: only its reference was retained.') : diagramMissing,
      '<pre>' + escape(raw) + '</pre>'));
  // Private-source images have no corresponding image file in the material package.
  text = text.replace(/!\[[^\]\n]*\]\(https:\/\/km\.sankuai\.com\/api\/file\/cdn\/[^)\n]*\)(?:\{[^}\n]*\})?/g,
    raw => missing(zh ? '图片缺失：图片文件未随材料保存。' : 'Image unavailable: its file was not retained with the material.', '<pre>' + escape(raw) + '</pre>'));
  text = text.replace(/:::heading\{[^}\n]*\blevel=([1-6])\b[^}\n]*\}[ \t]*\n([^\n]+)/g,
    (_, level, title) => '#'.repeat(Number(level)) + ' ' + title);
  text = text.replace(/:::title\{[^}\n]*\}[ \t]*\n([^\n]+)/g, (_, title) => '# ' + title);
  text = text.replace(/:::collapse\{[^}\n]*\}(?:\s*点击展开内容\s*---)?|:::note\{[^}\n]*\}/g, '');
  // Known inline wrappers affect presentation, not their enclosed wording.
  text = text.replace(/:\[(?:color|quote|font)\]\{[^}\n]*\}|\[\/(?:color|quote|font)\]/g, '');
  text = text.replace(/:\[link\]\{[^}\n]*href="([^"]+)"[^}\n]*\}([^\n]*?)\[\/link\]/g, (_, href, label) => '[' + label + '](' + href + ')');
  text = text.replace(/:\[open_link\]\{[^}\n]*href="([^"]+)"[^}\n]*\}/g, (_, href) => '[' + (zh ? '原链接' : 'Original link') + '](' + href + ')');
  text = text.replace(/:\[footnote\]\{[^}\n]*annotate="([^"]+)"[^}\n]*\}/g, (_, note) => '〔' + note + '〕');
  text = text.replace(/:\[mention\]\{[^}\n]*name="([^"]+)"[^}\n]*\}/g, (_, name) => name);
  let html = render(text);
  // Complete HTML tables were already decoded by the corpus builder; retain their rows and spans.
  html = html.replace(/(<t[dh](?:\s[^>]*)?>)([\s\S]*?)(<\/t[dh]>)/g, (_, open, cell, close) => open + marked.parseInline(cell) + close);
  return html.replace(/<!--material-fragment-(\d+)-->/g, (_, index) => blocks[Number(index) - 1]);
}

for (const [source, target] of routes) {
  const markdown = fs.readFileSync(path.join(sourceRoot, source), 'utf8');
  const title = markdown.split('\n')[0].replace(/^#\s+/, '').trim();
  const zh = target.includes('.zh-CN.');
  const catalog = source.startsWith('BROWSE');
  const description = zh ? title + '。保留已有材料、来源与历史版本，以及未核实和缺失内容说明。' : title + '. Existing material with source links, historical versions and unverified labels retained.';
  descriptions['materials/' + target] = description;
  const article = /^(reading|recovered)\/D-\d+\.md$/.test(source);
  const provenance = '<a href="' + sourceUrl + source + '">' + (zh ? '原始 Markdown' : 'Original Markdown') + '</a> · <a href="' + archive + '">' + (zh ? '全部历史版本' : 'All historical versions') + '</a>';
  // Join blank-separated table rows for display only; original Markdown stays unchanged.
  const render = text => marked.parse(text.replace(/\|\r?\n(?:[ \t]*\r?\n)+(?=\|)/g, '|\n'), {gfm: true});
  let content;
  if (article) {
    const reading = source.startsWith('reading/');
    const boundary = reading ? /^## /m.exec(markdown) : /^仅从同一保存版本恢复正文和完整单元格，不补写缺失内容。事实与发布日期仍按恢复说明判断。/m.exec(markdown);
    if (!boundary) throw new Error('Missing existing body boundary: ' + source);
    const start = boundary.index + (reading ? 0 : boundary[0].length);
    const titleEnd = markdown.indexOf('\n');
    const notes = markdown.slice(titleEnd, start).trim();
    const state = reading ? /^材料性质：([^。\n]+)/m.exec(notes)?.[1] : '恢复阅读稿，尚未核实';
    if (!state) throw new Error('Missing existing material status: ' + source);
    const correction = notes.includes('归属有误') ? ' · 含已知更正（见说明）' : '';
    content = render(markdown.slice(0, titleEnd)) +
      '<p class="material-status">' + escape(state + correction) + '</p>\n' +
      '<details class="material-notes"><summary>' + (zh ? '来源、历史版本与整理说明' : 'Sources, historical versions and notes') + '</summary>\n' +
      render(notes) + '<p>' + provenance + '</p></details>\n' +
      '<section class="material-body">' + renderBody(markdown.slice(start), render, zh) + '</section>\n';
  } else {
    content = render(markdown);
  }
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
<!-- discovery:start -->
<meta name="description" content="${escape(description)}">
<link rel="canonical" href="${site + target.replace(/index\.html$/, '')}">
${alternates}
<!-- discovery:end -->
<link rel="stylesheet" href="${assets}/showcase.css?v=site-20261015">
<link rel="stylesheet" href="${assets}/materials.css">
<script src="${assets}/reading-preferences.js?v=site-20261015"></script></head>
<body><main class="report-shell materials-reader${catalog ? ' materials-catalog' : ''}">
<nav class="report-nav" aria-label="${zh ? '阅读导航' : 'Reading navigation'}"><a data-home-link href="${home}">Research Toolkit</a><a href="${relative(target, 'index.zh-CN.html')}">中文目录</a><a href="${relative(target, 'index.html')}">English catalog</a></nav>
<article class="report-article">${content}</article>
${article ? '' : '<footer class="materials-provenance">' + provenance + '</footer>'}
</main></body></html>
`;
  const file = path.join(destination, target);
  fs.mkdirSync(path.dirname(file), {recursive: true});
  fs.writeFileSync(file, text);
}
fs.writeFileSync(path.join(destination, 'pages.json'), JSON.stringify({sourceRevision, descriptions, pairs: pairs.map(pair => pair.map(file => 'materials/' + file))}, null, 2) + '\n');
console.log('Exported ' + routes.size + ' static pages from existing Markdown to ' + destination);
